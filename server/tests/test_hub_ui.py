"""Exercise Hub navigation and controls in the real frontend with synthetic I/O."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from test_video_startup import ReadyRunner,record
from test_hub import loop_lesson,Sources
from lessontrace_site.adaptive import unit_state
from lessontrace_site.hub_sources import CATALOG,catalog
from lessontrace_site.main import create_app
from lessontrace_site.video_learning import blank_progress,public_state
from lessontrace_site.video_lessons import public_session
import asyncio

ROOT=Path(__file__).resolve().parents[2]


def fixture_records():
    video=record('1'*32);hub=copy.deepcopy(video);hub['lesson_id']='3'*32;hub['context']='hub'
    loader=Sources();docs=asyncio.run(loader.read('python-control-flow','nested-break','break'))
    chunks=docs.pop('chunks');sources=[c['id'] for c in chunks];spec=loop_lesson(sources)
    spec['units'][0]['prediction'].update(answer_index=0,verification={'output':'1\n3','runtime':'Synthetic UI fixture'})
    hub.update(title=spec['title'],answer=spec['answer'],sources=sources,curriculum=spec,caption_chunks=chunks,source_documents=[docs],
        url=CATALOG['python-control-flow']['url'],hub={'goal':'Understand an inner break','focus':'nested-break','base_lesson_id':video['lesson_id'],'rationale':'Follow the nearest loop, then try another input.',
        'path':[{'title':'Follow each loop','why':'Separate inner and outer changes.','evidence_ids':sources},{'title':'Change the input','why':'Practise with another row.','evidence_ids':sources}],
        'coverage':[{'concept':'Nearest loop','status':'supported','detail':'Supported by the selected synthetic passage.','evidence_ids':sources}],'differences':[],
        'steps':[{'action':'read_sources','detail':'Select the primary Python reference.'}]})
    results=[]
    for item in [video,hub]:
        progress=blank_progress(item);up=unit_state(progress,item['curriculum']['units'][0]['id']);up['phase']='exercise';up['quiz_skipped']=True
        results.append({'session':public_session(item),'learning':public_state(item,progress)})
    return results


@pytest.mark.parametrize('scenario',['build_switch','cancel','failed_research','reopen','retry_transport','retry_preparation','direct_hub'])
def test_hub_controls_sources_notes_and_separate_drafts(tmp_path,scenario):
    node=os.environ.get('LESSONTRACE_NODE') or shutil.which('node');jsdom=ROOT/'.local/frontend-check/node_modules/jsdom/lib/api.js'
    if not node or not jsdom.is_file():pytest.skip('Node and optional jsdom 26.1.0 are required; see scripts/README.md')
    app=create_app(tmp_path,runner=ReadyRunner())
    with TestClient(app) as client:
        responses={route:client.get(route).json() for route in ['/api/session','/api/lesson','/api/progress','/api/learning','/api/learning/functions','/api/coach']}
    responses['/media/timing.json']=[];responses['/api/session']['meta']['enabled']=True
    video,hub=fixture_records()
    fixture={'scenario':scenario,'responses':responses,'video':video,'hub':hub,'catalog':catalog(),'allowance':{'remaining_requests':10}}
    done=subprocess.run([node,str(Path(__file__).with_name('hub_ui.mjs')),str(ROOT),str(jsdom)],input=json.dumps(fixture),capture_output=True,text=True,encoding='utf-8',timeout=25)
    assert done.returncode==0,done.stdout+done.stderr
