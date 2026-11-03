"""Frozen-course replay, genuine prerequisite evidence and detached extras."""
import asyncio
import copy
import hashlib
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from test_video_learning import ROOT,run,scope
from lessontrace_site.main import create_app
from lessontrace_site.runner import WasiRunner
from lessontrace_site.course_catalog import VERSION,allowed_concepts,graph_digest
from lessontrace_site.course_placement import artifact
from lessontrace_site.video_learning import progress_key
from lessontrace_site.video_curriculum import validate_exercise


class NoCloud:
    enabled=False
    def __init__(self):self.calls=[]
    async def generate(self,*args,**kwargs):self.calls.append(args);raise AssertionError('Base course replay must not call Meta')


def synthetic_base():
    base=artifact('list_mutation');base['concept_id']='for_loop';base['version']=VERSION
    unit=base['curriculum']['units'][0];unit['id']='for-loop';unit['title']='Controlled for loop';needs=sorted(allowed_concepts('for_loop')-{'for_loop'})
    for field in ('exercise','fresh_exercise'):
        ex=unit[field];ex['parameters']=['values'];ex['entry']='result';ex['starter']='result = []';ex['reference_solution']='result = []\nfor value in values:\n    result.append(value)'
        ex['instructions']='Use a for loop to copy every supplied value into a new result list. Preserve values.'
        numbers=([2,3],[5],[]) if field=='exercise' else ([7,8],[0,1,2],[])
        ex['cases']=[{'arguments':[list(ns)],'expected':list(ns)} for ns in numbers];ex['needs']=needs;ex['targets']=['for_loop']
    for q in unit['quiz']+[unit['prediction']]:q.update(needs=needs,targets=['for_loop'])
    # Four tagged questions make independent wrong-question signals observable.
    unit['quiz']=[dict(unit['quiz'][0],prompt='Controlled understanding check '+str(i)) for i in range(4)]
    base['curriculum']['title']='Controlled shared base lesson';base['review_status']='draft';return base


@pytest.fixture
def course_browser(tmp_path):
    runner=WasiRunner(tmp_path);runner.cache=ROOT/'.local/wasi-cache';asyncio.run(runner.warmup());assert runner.ready
    base=synthetic_base()
    for field in ('exercise','fresh_exercise'):
        ex=base['curriculum']['units'][0][field];validated=asyncio.run(validate_exercise(ex,runner,base['curriculum']['sources']));validated.update(needs=ex['needs'],targets=ex['targets']);base['curriculum']['units'][0][field]=validated
    frozen=tmp_path/'frozen';frozen.mkdir();raw=json.dumps(base).encode();(frozen/'for_loop.json').write_bytes(raw)
    (frozen/'manifest.json').write_text(json.dumps({'version':VERSION,'status':'reviewed-pilot','graph_hash':graph_digest(),'lessons':{'for_loop':{'file':'for_loop.json','sha256':hashlib.sha256(raw).hexdigest()}}}))
    provider=NoCloud();app=create_app(tmp_path,runner=runner,provider=provider,course_content_root=frozen)
    with TestClient(app) as client:
        client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf'];yield client,provider,app,base


def owner(client):return hashlib.sha256(client.cookies['lessontrace_browser'].encode()).hexdigest()
def open_topic(client,concept):
    response=client.post('/api/course/open',json={'concept_id':concept});assert response.status_code==200,response.text
    course=client.get('/api/video-learning?context=course').json()['learning'];return course


def answer_all(client,app,course):
    record=app.state.store.progress(owner(client))['course_session'];unit=record['curriculum']['units'][0]
    for public,private in zip(course['unit']['quiz'],unit['quiz']+[unit['prediction']]):
        response=client.post('/api/video-learning/quiz',json=scope(course)|{'question_id':public['id'],'question_hash':public['question_hash'],'option':private['answer_index']})
        assert response.status_code==200,response.text
    return client.get('/api/video-learning?context=course').json()['learning']


def pass_concept(client,app,concept):
    course=open_topic(client,concept);course=answer_all(client,app,course)
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).json()['learning']
    private=app.state.store.progress(owner(client))['course_session']['curriculum']['units'][0]
    assert run(client,course,private['exercise']['reference_solution'],'exercise')['report']['all_passed']
    response=client.post('/api/video-learning/move',json=scope(course)|{'action':'fresh_check','consent':False,'request_id':str(uuid.uuid4())});assert response.status_code==200,response.text
    course=response.json()['learning'];passed=run(client,course,private['fresh_exercise']['reference_solution'],'exercise');assert passed['report']['independent_check']
    return course


def seed_known(client,app):
    needed=allowed_concepts('for_loop')-{'for_loop'}
    app.state.course_service.change(owner(client),lambda s:s['evidence'].update({c:{'version':VERSION,'basis':'Controlled test learner prerequisites'} for c in needed}))


def test_placement_checks_unlock_concepts_without_any_course_completion_or_api_call(course_browser):
    client,provider,app,_=course_browser
    blocked=client.post('/api/course/open',json={'concept_id':'for_loop'});assert blocked.status_code==409
    for concept in ('variables','arithmetic','strings','lists','list_mutation'):pass_concept(client,app,concept)
    board=client.get('/api/course').json();assert set(board['demonstrated'])=={'variables','arithmetic','strings','lists','list_mutation'}
    course=open_topic(client,'for_loop');assert course['context']=='course' and course['unit']['exercise']['kind']=='program'
    assert 'if_else' not in board['demonstrated'] and not provider.calls and board['allowance']['reserved_cents']==0
    assert 'reference_solution' not in client.get('/api/progress').text and 'course_session' not in client.get('/api/progress').text


def test_arithmetic_completion_explains_remaining_work_and_unlocks_only_after_independent_pass(course_browser):
    client,provider,app,_=course_browser;pass_concept(client,app,'variables')
    course=open_topic(client,'arithmetic');course=answer_all(client,app,course)
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).json()['learning']
    failed=run(client,course,'result = None\nleft = -2\nright = 2\nresult = left + right','exercise')
    assert [c['passed'] for c in failed['report']['checks']]==[False,False,True]
    def topic_view(board,name):return next(c for u in board['units'] for c in u['topics'] if c['id']==name)
    board=client.get('/api/course').json();status=topic_view(board,'arithmetic')['completion']
    assert status['stage']=='practice' and status['quiz_correct']==status['quiz_total']==2
    assert status['practice_checks_passed']==1 and status['practice_checks_total']==3
    assert '1 of 3' in status['message'] and not topic_view(board,'strings')['available']
    assert run(client,course,'result = left + right','exercise')['report']['all_passed']
    board=client.get('/api/course').json();assert topic_view(board,'arithmetic')['completion']['stage']=='independent'
    assert not topic_view(board,'strings')['available'],'Main practice alone must not unlock strings'
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'fresh_check','consent':False,'request_id':str(uuid.uuid4())}).json()['learning']
    assert run(client,course,'result = start - decrease','exercise')['report']['independent_check']
    board=client.get('/api/course').json();assert topic_view(board,'arithmetic')['completion']['stage']=='complete'
    assert topic_view(board,'strings')['available'] and board['next_concept']=='strings'
    assert set(board['demonstrated'])=={'variables','arithmetic'} and not provider.calls


def test_course_check_can_be_skipped_for_coding_but_not_for_progression(course_browser):
    client,provider,app,_=course_browser;seed_known(client,app);course=open_topic(client,'for_loop')
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'skip_quiz'}).json()['learning']
    record=app.state.store.progress(owner(client))['course_session'];ex=record['curriculum']['units'][0]['exercise']
    bypass=run(client,course,'result = values.copy()','exercise');assert not bypass['report']['all_passed'] and bypass['report']['skill_requirement']
    assert run(client,course,ex['reference_solution'],'exercise')['report']['all_passed']
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'fresh_check','consent':False,'request_id':str(uuid.uuid4())}).status_code==409
    assert not provider.calls


def test_shared_frozen_lesson_is_reused_and_unfinished_programs_still_run(course_browser):
    client,provider,app,_=course_browser;seed_known(client,app);course=open_topic(client,'for_loop');identifier=course['lesson_id']
    assert open_topic(client,'for_loop')['lesson_id']==identifier
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'skip_quiz'}).json()['learning']
    saved=run(client,course,'result = []','exercise');assert saved['status']=='complete' and not saved['report']['all_passed']
    bad=client.post('/api/video-learning/run',json=scope(course)|{'source':'result = []\nfor item in values:\n    if item > 0:\n        result.append(item)','mode':'exercise'})
    assert bad.status_code==422 and 'if_else' in bad.text
    assert not provider.calls


def test_owned_automatic_extra_waits_for_two_different_mistakes_and_never_replaces_base(course_browser):
    client,provider,app,base=course_browser;seed_known(client,app);course=open_topic(client,'for_loop');calls=[]
    class FakeAgent:
        async def prepare(self,*args,**kwargs):calls.append(kwargs);await asyncio.sleep(.02);return copy.deepcopy(base)
    app.state.course_service.agent=FakeAgent();app.state.course_service.meta.enabled=True
    assert client.post('/api/course/automatic-hub',json={'revision':0,'enabled':True,'consent':False}).status_code==409
    assert client.post('/api/course/automatic-hub',json={'revision':0,'enabled':True,'consent':True}).status_code==200
    first=course['unit']['quiz'][0]
    body=scope(course)|{'question_id':first['id'],'question_hash':first['question_hash'],'option':1}
    client.post('/api/video-learning/quiz',json=body);client.post('/api/video-learning/quiz',json=body)
    assert not client.get('/api/course').json()['extras'],'Repeating one wrong choice must not count as two different questions'
    second=course['unit']['quiz'][1]
    client.post('/api/video-learning/quiz',json=body|{'question_id':second['id'],'question_hash':second['question_hash']})
    for _ in range(80):
        board=client.get('/api/course').json()
        if board['extras']['for_loop']['status']=='ready':break
        time.sleep(.01)
    assert board['extras']['for_loop']['status']=='ready' and len(calls)==1
    assert set(calls[0]['signals'])=={'concept','wrong_questions','failed_practice_runs','requested_help'}
    assert app.state.store.progress(owner(client))['course_session']['lesson_id']==course['lesson_id']
    assert client.post('/api/course/extra/open',json={'concept_id':'for_loop'}).status_code==200
    extra=client.get('/api/video-learning?context=course').json()['learning'];assert extra['course_info']['course_role']=='extra'
    assert open_topic(client,'for_loop')['lesson_id']==course['lesson_id']
    client.cookies.clear();client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
    assert client.get('/api/course').json()['extras']=={} and client.get('/api/course/session').json()['session'] is None


def test_tampered_content_and_graph_are_blocked_before_serving(course_browser):
    client,_,app,_=course_browser;seed_known(client,app);root=app.state.course_service.content_root
    raw=(root/'for_loop.json').read_bytes();(root/'for_loop.json').write_bytes(raw+b' ')
    assert client.get('/api/course').status_code==503
    (root/'for_loop.json').write_bytes(raw);manifest=json.loads((root/'manifest.json').read_text());manifest['graph_hash']='0'*64;(root/'manifest.json').write_text(json.dumps(manifest))
    assert client.post('/api/course/open',json={'concept_id':'for_loop'}).status_code==503


def test_failed_extra_gets_one_explicit_retry_and_preserves_reservations(course_browser):
    client,_,app,base=course_browser;seed_known(client,app);course=open_topic(client,'for_loop');service=app.state.course_service;service.meta.enabled=True;count=[]
    class Agent:
        async def prepare(self,who,*args,**kwargs):
            count.append(1);service.store.reserve_provider(who,'controlled failed course extra')
            if len(count)==1:raise ValueError('Controlled provider failure')
            return copy.deepcopy(base)
    service.agent=Agent();body={'concept_id':'for_loop','lesson_id':course['lesson_id'],'consent':True}
    assert client.post('/api/course/extra',json=body).status_code==200
    for _ in range(80):
        if client.get('/api/course').json()['extras']['for_loop']['status']=='failed':break
        time.sleep(.01)
    assert len(count)==1 and service.store.provider_allowance()['reserved_cents']==10
    client.post('/api/course/extra',json=body);assert len(count)==1
    assert client.post('/api/course/extra',json=body|{'retry':True,'consent':False}).status_code==409
    client.post('/api/course/extra',json=body|{'retry':True})
    for _ in range(80):
        if client.get('/api/course').json()['extras']['for_loop']['status']=='ready':break
        time.sleep(.01)
    assert len(count)==2 and service.store.provider_allowance()['reserved_cents']==20
    client.post('/api/course/extra',json=body|{'retry':True});assert len(count)==2


def test_fresh_check_stays_quiet_and_stale_answers_cannot_change_it(course_browser):
    client,_,app,_=course_browser;seed_known(client,app);course=open_topic(client,'for_loop');course=answer_all(client,app,course)
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).json()['learning'];record=app.state.store.progress(owner(client))['course_session'];unit=record['curriculum']['units'][0]
    run(client,course,unit['exercise']['reference_solution'],'exercise')
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'fresh_check','consent':False,'request_id':str(uuid.uuid4())}).json()['learning']
    assert client.post('/api/course/automatic-hub',json={'revision':0,'enabled':True,'consent':True}).status_code==200
    assert client.post('/api/course/extra',json={'concept_id':'for_loop','lesson_id':course['lesson_id'],'consent':True}).status_code==409
    q=course['unit']['quiz'][0];assert client.post('/api/video-learning/quiz',json=scope(course)|{'question_id':q['id'],'question_hash':q['question_hash'],'option':1}).status_code==409
    prediction=course['unit']['prediction'];assert client.post('/api/video-learning/predict',json=scope(course)|{'source_hash':prediction['source_hash'],'option':0}).status_code==409
    assert client.get('/api/course').json()['extras']=={}
    passed=run(client,course,unit['fresh_exercise']['reference_solution'],'exercise');assert passed['report']['independent_check']
    assert client.get('/api/course').json()['signals']['quiet'] is False,'A completed independent check must allow the learner to open a ready follow-up.'
