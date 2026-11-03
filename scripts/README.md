# Development checks

Run from the repository root with the standalone `.venv` created by the README.

```powershell
$env:PYTHONPATH='server'
npm install --prefix .local/frontend-check jsdom@26.1.0
.\.venv\Scripts\python.exe -m pytest server/tests -q
```

If Node is not on PATH, set `LESSONTRACE_NODE` to its executable. Without Node/jsdom, browser-flow cases are explicitly skipped. They are controlled-I/O DOM checks, not native browser visual acceptance. Python execution tests use the real WASI runtime.

To rebuild the committed editor:

```powershell
npm ci --prefix editor
node editor/build.mjs
```

To prepare an audit of the frozen course without any Meta request:

```powershell
.\.venv\Scripts\python.exe scripts/review_frozen_course.py --concept variables
```

Only an explicit `--live` audit uses your own key and records local reservations. Routine release tests do not consume Meta credits. Test examples and simulated model results must never be presented as real provider outputs.
