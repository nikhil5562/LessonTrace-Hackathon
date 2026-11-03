"""Real frontend controls and persistence events with isolated synthetic I/O."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from test_video_startup import ReadyRunner
from test_hub_ui import fixture_records
from lessontrace_site.main import create_app
from lessontrace_site.learning_coach import defaults

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('scenario',['preferences','library','research','fresh','conflict','unavailable','network','evidence','exhausted','last-reservation','resumed'])
def test_learning_coach_interface(tmp_path,scenario):
    node=os.environ.get('LESSONTRACE_NODE') or shutil.which('node');jsdom=ROOT/'.local/frontend-check/node_modules/jsdom/lib/api.js'
    if not node or not jsdom.is_file():pytest.skip('Node and optional jsdom 26.1.0 required')
    app=create_app(tmp_path,runner=ReadyRunner())
    with TestClient(app) as client:
        routes=['/api/session','/api/lesson','/api/progress','/api/learning','/api/learning/functions']
        responses={route:client.get(route).json() for route in routes}
    responses['/media/timing.json']=[];responses['/api/session']['meta']['enabled']=True
    video,hub=fixture_records()
    fixture={'scenario':scenario,'responses':responses,'video':video,'hub':hub,'preferences':defaults()['preferences']}
    done=subprocess.run([node,str(Path(__file__).with_name('coach_ui.mjs')),str(ROOT),str(jsdom)],input=json.dumps(fixture),capture_output=True,text=True,encoding='utf-8',timeout=25)
    assert done.returncode==0,done.stdout+done.stderr
