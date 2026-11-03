"""Real DOM scripts with controlled I/O; not live Meta inference."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest

def test_original_sample_and_safe_request_status_ui():
    root=Path(__file__).resolve().parents[2]
    node=os.environ.get('LESSONTRACE_NODE') or shutil.which('node')
    jsdom=root/'.local/frontend-check/node_modules/jsdom/lib/api.js'
    if not node or not jsdom.is_file():pytest.skip('Optional Node and jsdom 26.1.0 required')
    run=subprocess.run([node,str(root/'server/tests/demo_tools.mjs'),str(jsdom)],capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stdout+run.stderr
