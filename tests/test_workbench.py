import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workbench.core import Queue, parse_json
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from quick_poll import is_complete


class FakeCLI:
    def __init__(self): self.runs = 0; self.fail = False
    def call(self, *args, **kwargs):
        if args[0] == 'model': return {'matches': [{'modelName': 'Test'}]}
        if args[0] == 'download':
            Path(args[args.index('-o')+1], 'test.png').write_bytes(b'fixture')
            return 'test.png'
        if self.fail: raise TimeoutError('connection lost')
        return {'nodeKey': 'test-node', 'data': {'taskInfo': {'status': 2}, 'url': ['result']}}
    def generate(self, *args):
        self.runs += 1
        if self.fail: raise TimeoutError('generation accepted, response lost')
        return {'status': 2}


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cli = FakeCLI()
        self.q = Queue(self.temp.name, self.cli)
    def tearDown(self): self.temp.cleanup()
    def add(self):
        return self.q.add(dict(project='project123', model='Test', kind='image', prompts=['one'], params={}))[0]
    def test_complete_download_and_manifest(self):
        job = self.add(); self.q.process(job['id'])
        self.assertEqual(self.q.get(job['id'])['status'], 'complete')
        self.assertTrue(Path(self.temp.name, 'outputs', job['id'], 'task.json').exists())
        self.assertEqual(self.cli.runs, 1)
    def test_restart_does_not_resubmit_uncertain_generation(self):
        job = self.add(); self.q.update(job['id'], status='running', node='test-node')
        recovered = Queue(self.temp.name, self.cli)
        recovered.process(job['id'])
        self.assertEqual(recovered.get(job['id'])['status'], 'needs_review')
        recovered.reconcile(job['id'])
        self.assertEqual(recovered.get(job['id'])['status'], 'complete')
        self.assertEqual(self.cli.runs, 0)
    def test_creation_timeout_never_generates(self):
        job=self.add(); self.cli.fail=True; self.q.process(job['id'])
        self.q.process(job['id'])
        self.assertEqual(self.q.get(job['id'])['status'], 'needs_review')
        self.assertEqual(self.cli.runs, 0)
    def test_cancelled_job_never_runs(self):
        job=self.add(); self.q.cancel(job['id']); self.q.process(job['id'])
        self.assertEqual(self.cli.runs, 0)
    def test_insufficient_credits_pauses_queue(self):
        job=self.add()
        with patch.object(self.cli, 'generate', side_effect=RuntimeError('1200000136 算力不足')):
            self.q.process(job['id'])
        self.assertEqual(self.q.get(job['id'])['status'], 'failed')
        self.assertTrue(self.q.paused_file.exists())
    def test_invalid_batch_has_no_partial_writes(self):
        with self.assertRaises(ValueError):
            self.q.add(dict(project='project123', model='Test', kind='image', prompts=['ok','']))
        self.assertEqual(self.q.jobs(), [])
    def test_poll_ignores_progress_language(self):
        for text in ['正在生成', '完成后通知你', '请访问 https://example.com 查看进度']:
            self.assertFalse(is_complete({'content':text}))
        self.assertTrue(is_complete({'status':'completed','artifacts':[{'url':'https://example.com/result.png'}]}))
    def test_cli_json_with_progress(self):
        self.assertEqual(parse_json('[run] progress=100%\n{"status":2}'), {'status':2})


if __name__ == '__main__': unittest.main()
