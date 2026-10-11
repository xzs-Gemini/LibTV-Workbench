"""Durable local queue. No credentials, shell commands, or automatic paid retries."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = os.environ.get("LIBTV_PROJECT", "")


def parse_json(output):
    # Some CLI versions put progress lines before their JSON document.
    for pos, char in enumerate(output):
        if char == "{":
            try:
                return json.JSONDecoder().raw_decode(output[pos:])[0]
            except ValueError:
                continue
    raise ValueError("CLI 未返回可识别的 JSON；请查看任务详情")


def redact(text):
    text = re.sub(r"(?i)(bearer\s+|(?:access[_-]?token|token|authorization|access[_-]?key)\s*[:=]\s*)[^\s,\"}]+", r"\1[已隐藏]", str(text))
    return text[-1600:]


class CLI:
    def __init__(self, path=None):
        bundled = ROOT / ".tools/libtv-1.0.2/libtv-win-x64/libtv.exe"
        self.path = str(path or os.environ.get("LIBTV_CLI") or (bundled if bundled.exists() else shutil.which("libtv") or bundled))

    def call(self, *args, timeout=60, raw=False):
        try:
            result = subprocess.run([self.path, *map(str, args)], cwd=ROOT, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("CLI 请求超时，远端可能仍在执行；请核对状态") from exc
        if result.returncode:
            raise RuntimeError(redact(result.stderr or result.stdout))
        return result.stdout.strip() if raw else parse_json(result.stdout)

    def generate(self, node, project, progress):
        # The CLI itself waits for completion. File streams prevent pipe deadlocks.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen([self.path, "node", node, "-p", project, "--run"], cwd=ROOT,
                                    stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            start = time.monotonic()
            try:
                while proc.poll() is None:
                    if time.monotonic() - start > 1800:
                        raise TimeoutError("生成等待超过 30 分钟，请核对远端状态")
                    # Read through a separate handle offset; never move writer's position.
                    progress(None)
                    time.sleep(2)
                out.seek(0); err.seek(0)
                stdout, stderr = out.read().decode("utf-8"), err.read().decode("utf-8")
                if proc.returncode:
                    raise RuntimeError(redact(stderr or stdout))
                return parse_json(stdout)
            finally:
                if proc.poll() is None:
                    proc.kill(); proc.wait()


class Queue:
    def __init__(self, directory=None, cli=None, recover=True):
        self.directory = Path(directory or ROOT / "data").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "tasks.sqlite3"
        self.cli = cli or CLI()
        self.stop = threading.Event()
        self.paused_file = self.directory / "queue-paused"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        # A restart cannot establish whether a remote write was accepted.
        for job in self.jobs() if recover else []:
            if job["status"] in ("creating", "running", "downloading", "checking"):
                self.update(job["id"], status="needs_review", error="程序曾中断，请点击核对状态；不会自动重复生成")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def jobs(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM jobs ORDER BY rowid DESC")]

    def get(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("任务不存在")
        return json.loads(row[0])

    def update(self, ident, **changes):
        with self.lock, self.connect() as db:
            job = self.get(ident)
            job.update(changes, updated=time.time())
            db.execute("UPDATE jobs SET body=? WHERE id=?", (json.dumps(job, ensure_ascii=False), ident))
        return job

    def add(self, body):
        project, model, kind = body.get("project", ""), body.get("model", ""), body.get("kind", "")
        prompts = body.get("prompts")
        params = body.get("params", {})
        if not re.fullmatch(r"[A-Za-z0-9-]{8,80}", project):
            raise ValueError("请选择有效项目")
        if kind not in ("image", "video") or not isinstance(model, str) or not model or len(model) > 120:
            raise ValueError("请选择图片或视频模型")
        if not isinstance(prompts, list) or not 1 <= len(prompts) <= 20 or any(not isinstance(p, str) or not p.strip() or len(p) > 10000 for p in prompts):
            raise ValueError("一次提交 1–20 条需求，每条最多 10000 字")
        if not isinstance(params, dict) or len(params) > 30 or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", k) or k in ("model", "prompt") for k in params):
            raise ValueError("生成参数格式不正确")
        models = self.cli.call("model", "search", "-t", kind).get("matches", [])
        if model not in [m.get("modelName") for m in models]:
            raise ValueError("该模型已不可用，请刷新列表")
        created = []
        with self.lock, self.connect() as db:
            for prompt in prompts:
                ident = uuid.uuid4().hex
                job = dict(id=ident, name="wb-" + ident, project=project, model=model, kind=kind,
                           prompt=prompt.strip(), params=params, status="queued", node=None,
                           progress=0, error="", files=[], created=time.time(), updated=time.time())
                db.execute("INSERT INTO jobs VALUES (?, ?)", (ident, json.dumps(job, ensure_ascii=False)))
                created.append(job)
        return created

    def cancel(self, ident):
        with self.lock:
            if self.get(ident)["status"] != "queued":
                raise ValueError("只能取消尚未提交到云端的任务")
            return self.update(ident, status="cancelled")

    def download(self, job):
        directory = self.directory / "outputs" / job["id"]
        directory.mkdir(parents=True, exist_ok=True)
        self.update(job["id"], status="downloading", progress=100)
        self.cli.call("download", "-n", job["node"], "-p", job["project"], "-o", directory, timeout=300, raw=True)
        files = [p.name for p in directory.iterdir() if p.is_file() and p.stat().st_size > 0]
        if not files:
            raise RuntimeError("生成已结束，但下载目录为空；请核对状态后重新下载")
        (directory / "task.json").write_text(json.dumps({k: job[k] for k in ("id", "project", "node", "kind", "model", "prompt", "params")}, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.update(job["id"], status="complete", progress=100, files=files, error="")

    def reconcile(self, ident):
        with self.lock:
            job = self.get(ident)
            if job["status"] not in ("needs_review", "failed", "complete"):
                raise ValueError("任务正在处理，请稍后再核对")
            self.update(ident, status="checking")
        try:
            node = self.cli.call("node", job["node"] or job["name"], "-p", job["project"])
            job = self.update(ident, node=node["nodeKey"])
            data = node.get("data", {})
            info = data.get("taskInfo", {})
            if info.get("status") == 2 and data.get("url"):
                return self.download(job)
            return self.update(ident, status="needs_review", progress=info.get("progressPercent", 0),
                               error="远端尚无可下载结果。可稍后再次核对；不会自动重新生成。")
        except Exception as exc:
            return self.update(ident, status="needs_review", error=redact(exc))

    def process(self, ident):
        try:
            with self.lock:
                job = self.get(ident)
                if job["status"] not in ("queued", "ready"):
                    return
                if job["status"] == "queued":
                    self.update(ident, status="creating")
            if not job["node"]:
                args = ["node", "create", job["name"], "-p", job["project"], "-t", job["kind"], "--prompt", job["prompt"], "-s", "model=" + job["model"]]
                for key, val in job["params"].items():
                    args.extend(["-s", key + "=" + (val if isinstance(val, str) else json.dumps(val))])
                node = self.cli.call(*args)
                job = self.update(ident, status="ready", node=node["nodeKey"])
            self.update(ident, status="running", started=time.time())
            last_poll = [0]
            def progress(_):
                if time.monotonic() - last_poll[0] < 8:
                    return
                last_poll[0] = time.monotonic()
                try:
                    state = self.cli.call("node", job["node"], "-p", job["project"], timeout=10)
                    self.update(ident, progress=state.get("data", {}).get("taskInfo", {}).get("progressPercent", 0))
                except Exception:
                    pass  # a transient read failure must never trigger another generation
            result = self.cli.generate(job["node"], job["project"], progress)
            status = result.get("status", result.get("data", {}).get("taskInfo", {}).get("status"))
            if status != 2:
                raise RuntimeError("云端未返回成功状态，请核对状态")
            self.download(job)
        except Exception as exc:
            message = redact(exc)
            if "1200000136" in message or "算力不足" in message:
                self.paused_file.write_text("LibTV 算力不足，队列已暂停", encoding="utf-8")
                self.update(ident, status="failed", error="LibTV 账号算力不足，本次生成未开始。处理额度后可重新提交这条需求。后续队列已暂停。")
            else:
                self.update(ident, status="needs_review", error=message)

    def run(self):
        while not self.stop.is_set():
            jobs = [j for j in reversed(self.jobs()) if j["status"] in ("queued", "ready")]
            if jobs and not self.paused_file.exists():
                self.process(jobs[0]["id"])
            else:
                self.stop.wait(1)
