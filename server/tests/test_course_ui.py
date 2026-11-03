"""Actual browser scripts with controlled I/O; not native visual acceptance."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_course_workflow import course_browser,seed_known,open_topic,owner
from lessontrace_site import adaptive
from lessontrace_site.video_learning import progress_key,public_state


@pytest.mark.parametrize('scenario',['overview','program','fresh','trace','progress','lesson-first'])
def test_course_journey_interface(course_browser,scenario):
    client,_,app,_=course_browser;root=Path(__file__).resolve().parents[2]
    node=os.environ.get('LESSONTRACE_NODE') or shutil.which('node');jsdom=root/'.local/frontend-check/node_modules/jsdom/lib/api.js'
    if not node or not jsdom.is_file():pytest.skip('Node and optional jsdom 26 required')
    if scenario=='lesson-first':
        from test_lesson_first import use_teaching_flow
        use_teaching_flow(app)
    seed_known(client,app);course=open_topic(client,'for_loop');record=app.state.store.progress(owner(client))['course_session'];unit=record['curriculum']['units'][0]
    up=app.state.store.progress(owner(client))[progress_key(record['lesson_id'])];state=adaptive.unit_state(up,unit['id']);state['phase']='lesson' if scenario=='lesson-first' else 'exercise';state['practice_passed']=scenario!='lesson-first';state['activities']['practice']['passed']=scenario!='lesson-first'
    for q in ([] if scenario=='lesson-first' else course['unit']['quiz']):state['quiz_answers'][q['id']]={'question_hash':q['question_hash'],'option':0 if q['id']!='prediction' else 1,'correct':True,'at':0}
    course=public_state(record,up);fresh_progress=copy.deepcopy(up);fstate=adaptive.unit_state(fresh_progress,unit['id']);adaptive.activate(fstate,{'id':'frozen-fixture','kind':'fresh','frozen':True,'exercise':dict(unit['fresh_exercise'],starter='result = None'),'opening_question':'Try the different task.'});fresh=public_state(record,fresh_progress)
    paths=['/api/session','/api/lesson','/api/progress','/api/learning','/api/learning/functions']
    responses={p:client.get(p).json() for p in paths};responses['/media/timing.json']=[]
    fixture={'scenario':scenario,'board':client.get('/api/course').json(),'session':client.get('/api/course/session').json()['session'],'learning':course,'fresh':fresh,'coach':client.get('/api/coach',params={'lesson_id':record['lesson_id']}).json(),'responses':responses}
    if scenario=='trace':
        source='result = 1\nresult = 2';fixture['learning']['unit']['exercise'].update(starter=source,parameters=['left','right'],input_example={'left':2,'right':3})
        fixture['learning']['progress']['last_run_id']='display-fixture'
        fixture['run']={'id':'display-fixture','status':'complete','source':source,'report':{'lesson_id':record['lesson_id'],'unit_id':unit['id'],'source_hash':'0'*64,'runtime':'Controlled display fixture','trace_case':1,'all_passed':False,'actual':2,'output':'',
            'checks':[{'input':[2,3],'expected':5,'actual':2,'passed':False},{'input':[0,4],'expected':4,'actual':2,'passed':False}],
            'trace':[{'line':i,'kind':'line','frames':[{'name':'<module>','bindings':{n:{'kind':'scalar','value':v} for n,v in [('left',0),('right',4),('result',i)]}}],'objects':{},'loops':[],'output':''} for i in (1,2)]}}
    if scenario=='progress':
        item=next(c for u in fixture['board']['units'] for c in u['topics'] if c['id']=='for_loop')
        item['completion']={'stage':'practice','quiz_correct':2,'quiz_total':2,'practice_passed':False,'practice_checks_passed':1,'practice_checks_total':3,'independent_passed':False,'message':'Main practice: 1 of 3 checks passed. Fix the remaining checks, then try the independent task.'}
    result=subprocess.run([node,str(Path(__file__).with_name('course_ui.mjs')),str(root),str(jsdom)],input=json.dumps(fixture),capture_output=True,text=True,encoding='utf-8',timeout=25)
    assert result.returncode==0,result.stdout+result.stderr
