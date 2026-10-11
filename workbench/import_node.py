"""Import and download an already generated node; never starts a generation."""
import argparse
import json
import time
import uuid
from .core import Queue

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project'); parser.add_argument('node')
    args = parser.parse_args()
    queue = Queue(recover=False)
    node = queue.cli.call('node', args.node, '-p', args.project)
    data = node['data']; params = data.get('params', {})
    job = dict(id=uuid.uuid4().hex, name=data.get('name','已生成素材'), project=args.project,
               model=params.get('model',''), kind=data['type'], prompt=params.get('prompt',''),
               params=params.get('settings',{}), status='needs_review', node=node['nodeKey'],
               progress=0, error='', files=[], created=time.time(), updated=time.time())
    with queue.connect() as db:
        db.execute('INSERT INTO jobs VALUES (?, ?)', (job['id'], json.dumps(job, ensure_ascii=False)))
    result = queue.reconcile(job['id'])
    print(json.dumps({'id':result['id'], 'status':result['status'], 'files':result['files']}, ensure_ascii=False))
