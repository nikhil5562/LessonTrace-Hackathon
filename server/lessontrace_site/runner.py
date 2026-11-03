"""Real CPython in a WASI capability boundary, with no host grants or tools."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime"
if RUNTIME.is_dir() and str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))


class ExecutionUnavailable(RuntimeError):
    pass


class WasiRunner:
    def __init__(self, data_dir: Path):
        self.cache = data_dir / "wasi-cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lessontrace-wasi")
        self.ready = False
        self.error = None
        self.harness = Path(__file__).with_name("guest.py").read_text(encoding="utf-8")

    async def call(self, code, stdin=b"", fuel=None):
        import wasi_python
        return await wasi_python.run_async(["-c", code], stdin=stdin, root=False,
            grants=(), mounts=(), host=None, env={}, import_path=(),
            fuel=fuel, deadline_s=5.0, memory_bytes=256 * 1024 * 1024,
            output_bytes=2 * 1024 * 1024, cache_dir=self.cache,
            executor=self.executor, max_open_files=32)

    async def warmup(self):
        try:
            done = await self.call("print('lessontrace-ready')")
            self.ready = done.exit_code == 0 and done.stdout.strip() == b"lessontrace-ready"
            if not self.ready:
                self.error = "Python could not initialise within the configured execution limits."
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.error = "Python runtime is unavailable (" + type(error).__name__ + ")."

    async def execute(self, payload):
        if not self.ready:
            raise ExecutionUnavailable(self.error or "Python is warming up. Try again shortly.")
        done = await self.call(self.harness, json.dumps(payload).encode())
        if done.trapped:
            return {"error": {"type": "ExecutionLimit", "message": "Execution stopped: " + str(done.trapped)}}
        if done.exit_code != 0 or done.truncated:
            return {"error": {"type": "ExecutionError", "message": "Python could not finish within the pilot limits."}}
        try:
            result = json.loads(done.stdout)
            if not isinstance(result, dict):
                raise ValueError
            return result
        except (ValueError, UnicodeDecodeError):
            return {"error": {"type": "ExecutionError", "message": "Python returned an invalid trace."}}

    async def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
