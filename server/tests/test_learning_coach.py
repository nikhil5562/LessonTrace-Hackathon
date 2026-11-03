"""Owned continuity and opted-in follow-ups; synthetic Meta, actual CPython checks."""
import copy
import hashlib
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from test_hub import hub_browser,ready,finished
from test_video_learning import prepare,scope,run as execute
from lessontrace_site import adaptive
from lessontrace_site.learning_coach import defaults,loops_supported
from lessontrace_site.video_learning import progress_key


@pytest.fixture
def coach_browser(hub_browser):
    client,provider,loader,app=hub_browser
    app.state.store.provider_limit_cents=1500
    return client,provider,loader,app


def who(client):return hashlib.sha256(client.cookies.get('lessontrace_browser').encode()).hexdigest()
def run(client,course,source):return execute(client,course,source,'exercise')
def dashboard(client,course=None):return client.get('/api/coach',params={'lesson_id':course['lesson_id']} if course else {}).json()
def practice(client):
    ready(client)
    course=client.get('/api/video-learning?context=hub').json()['learning']
    response=client.post('/api/video-learning/move',json=scope(course)|{'action':'skip_quiz'})
    assert response.status_code==200,response.text
    return response.json()['learning']
def prefs(client,**changes):
    body=dashboard(client)['preferences']|changes
    response=client.post('/api/coach/preferences',json=body);assert response.status_code==200,response.text
    return response.json()['preferences']
def permission(client,course,enabled=True,consent=True):
    return client.post('/api/coach/research-permission',json={'lesson_id':course['lesson_id'],'unit_id':course['unit']['id'],'enabled':enabled,'consent':consent})
def private_progress(client,app,course):return app.state.store.progress(who(client))[progress_key(course['lesson_id'])]
def put_progress(client,app,course,progress):app.state.store.set_progress(who(client),progress_key(course['lesson_id']),progress)
def chat(client,course,text='I expected both loops to end after the first match.'):
    body=scope(course)|{'text':text,'source':course['unit']['exercise']['starter'],'step':0,'consent':True,'intent':'reply','request_id':str(uuid.uuid4())}
    response=client.post('/api/video-learning/coach',json=body);assert response.status_code==200,response.text
    return response.json()


def test_confirmed_preferences_version_privacy_and_no_provider_call(coach_browser):
    client,provider,_,app=coach_browser
    assert dashboard(client)['preferences']==defaults()['preferences']
    before=app.state.store.provider_allowance()
    p=prefs(client,goal='Understand loops independently',explanation='short_steps',representation='boxes')
    assert p['revision']==1 and not provider.calls and not provider.research_calls
    assert client.post('/api/coach/preferences',json=p|{'revision':0}).status_code==409
    assert 'coach_state' not in client.get('/api/progress').text
    other=TestClient(app)
    other.get('/api/session');assert dashboard(other)['preferences']['goal']==''
    assert other.post('/api/coach/preferences',json=p).status_code==403
    assert app.state.store.provider_allowance()==before
    result=prepare(client,answer_lesson_checks=False)
    assert provider.calls[-1]['learner_preferences']['goal']==p['goal']
    assert dashboard(client,result['learning'])['current']['stage']=='quiz'


def test_saved_lessons_resume_ownership_and_erasure_keep_credit_records(coach_browser):
    client,_,_,app=coach_browser
    first=prepare(client)['learning'];second=prepare(client)['learning']
    library=dashboard(client)['lessons'];assert {x['lesson_id'] for x in library}=={first['lesson_id'],second['lesson_id']}
    old=private_progress(client,app,first)
    result=client.post('/api/coach/resume',json={'lesson_id':first['lesson_id']})
    assert result.status_code==200 and result.json()['session']['lesson_id']==first['lesson_id']
    assert private_progress(client,app,first)==old
    other=TestClient(app)
    other.headers['X-LessonTrace-CSRF']=other.get('/api/session').json()['csrf']
    assert other.post('/api/coach/resume',json={'lesson_id':first['lesson_id']}).status_code==404
    assert other.get('/api/coach',params={'lesson_id':first['lesson_id']}).status_code==404
    for private in ['reference_solution','answer_index','caption_chunks','curriculum','expected_output']:
        assert '"'+private+'"' not in json.dumps(dashboard(client))
    before=app.state.store.provider_allowance();app.state.store.delete_owner(who(client))
    assert not app.state.store.lesson_list(who(client)) and not dashboard(client)['lessons']
    assert app.state.store.provider_allowance()==before


def test_opt_in_two_failed_runs_and_stated_expectation_prepare_once_detached(coach_browser):
    client,provider,_,app=coach_browser
    course=practice(client);original=client.get('/api/hub').json()['session']
    assert permission(client,course,consent=False).status_code==409
    assert permission(client,course).status_code==200
    run(client,course,course['unit']['exercise']['starter']);run(client,course,course['unit']['exercise']['starter'])
    assert len(provider.research_calls)==3
    assert dashboard(client,course)['next_step']['kind']=='expectation'
    chat(client,course)
    grant=dashboard(client,course)['research'];assert grant['used'] and grant['job']['detached']
    done=finished(client,grant['job']['id']);assert done['job']['status']=='ready',done
    assert len(provider.research_calls)==6
    assert client.get('/api/hub').json()['session']==original
    assert client.get('/api/hub').json()['prepared_session']['lesson_id']==done['session']['lesson_id']
    assert client.get('/api/video-learning?context=hub').json()['learning']['lesson_id']==course['lesson_id']
    state=dashboard(client,course);assert state['next_step']['kind']=='research_ready'
    repeated=client.post('/api/coach/research',json={'lesson_id':course['lesson_id'],'unit_id':course['unit']['id'],'consent':True})
    assert repeated.status_code==200 and len(provider.research_calls)==6
    evidence=provider.research_calls[-1]['current_lesson']
    assert evidence['attempt_summary']['failures']==2 and 'expected both loops' in evidence['attempt_summary']['learner_expectation']
    assert 'current_code' not in evidence and 'reference_solution' not in json.dumps(evidence)
    assert client.post('/api/coach/resume',json={'lesson_id':done['session']['lesson_id']}).status_code==200
    assert client.get('/api/video-learning?context=hub').json()['learning']['lesson_id']==done['session']['lesson_id']
    assert private_progress(client,app,course)['units'][course['unit']['id']]['activities']['practice']['failures']==2


def test_no_opt_in_no_expectation_or_quiz_errors_do_not_start_research(coach_browser):
    client,provider,_,app=coach_browser
    course=practice(client)
    run(client,course,course['unit']['exercise']['starter']);run(client,course,course['unit']['exercise']['starter']);chat(client,course)
    assert len(provider.research_calls)==3 and not dashboard(client,course)['research'].get('used')
    progress=private_progress(client,app,course);up=adaptive.unit_state(progress,course['unit']['id'])
    up['phase']='prediction';adaptive.active(up)['failures']=0;put_progress(client,app,course,progress)
    assert permission(client,course).status_code==200
    assert not dashboard(client,course)['research'].get('used')
    for _ in range(3):dashboard(client,course)
    assert len(provider.research_calls)==3


def test_fresh_check_is_quiet_and_research_cannot_unlock_it(coach_browser):
    client,provider,_,app=coach_browser
    course=practice(client);before=len(provider.research_calls)
    progress=private_progress(client,app,course);up=adaptive.unit_state(progress,course['unit']['id'])
    # Use an isolated progress fixture to check the boundary, not to award learner evidence.
    exercise=copy.deepcopy(app.state.store.saved_lesson(who(client),course['lesson_id'])['curriculum']['units'][0]['exercise'])
    adaptive.activate(up,{'id':uuid.uuid4().hex,'kind':'fresh','exercise':exercise,'opening_question':'Try this task yourself.','created':time.time()})
    put_progress(client,app,course,progress)
    assert dashboard(client,course)['next_step']['kind']=='quiet'
    assert permission(client,course).status_code==409
    result=client.post('/api/coach/research',json={'lesson_id':course['lesson_id'],'unit_id':course['unit']['id'],'consent':True})
    assert result.status_code==409 and len(provider.research_calls)==before


def test_manual_followup_budget_cancellation_and_preference_reset(coach_browser):
    client,provider,loader,app=coach_browser
    course=practice(client);loader.delay=.5
    app.state.store.provider_limit_cents=60
    body={'lesson_id':course['lesson_id'],'unit_id':course['unit']['id'],'consent':True}
    before=app.state.store.provider_allowance();response=client.post('/api/coach/research',json=body)
    assert response.status_code==409 and app.state.store.provider_allowance()==before
    app.state.store.provider_limit_cents=1500
    assert client.post('/api/coach/research',json=body|{'consent':False}).status_code==409
    result=client.post('/api/coach/research',json=body);assert result.status_code==200,result.text
    identifier=result.json()['research']['job']['id'];reserved=app.state.store.provider_allowance()['reserved_cents']
    response=client.post('/api/coach/preferences/reset',json={'revision':0});assert response.status_code==200
    assert finished(client,identifier)['job']['status']=='cancelled'
    assert app.state.store.provider_allowance()['reserved_cents']>=reserved
    assert dashboard(client,course)['current']['stage']=='practice'


def test_meta_can_choose_pre_authorised_research_but_not_on_fresh_checks(coach_browser):
    client,provider,_,_=coach_browser
    course=practice(client);assert permission(client,course).status_code==200
    provider.action='research_topic';result=chat(client,course,'Please compare another explanation before I try this loop.')
    assert 'research_topic' in provider.calls[-1]['available_actions']
    assert result['message']['action_result']['kind']=='research_topic' and 'preparing' in result['message']['text']
    job=dashboard(client,course)['research']['job'];assert finished(client,job['id'])['job']['status']=='ready'
    assert not dashboard(client,course)['current']['independent_passed']


def test_goal_change_pauses_permissions_and_scopes_to_exact_concept(coach_browser):
    client,_,_,app=coach_browser;course=practice(client)
    permission(client,course)
    prefs(client,goal='I want to practise a different goal')
    assert not dashboard(client,course)['research']['enabled']
    assert permission(client,course|{'unit':course['unit']|{'id':'old-concept'}}).status_code==409
    record=app.state.store.saved_lesson(who(client),course['lesson_id'])
    unit=copy.deepcopy(record['curriculum']['units'][0]);unit.update(title='A form for a website',explanation='Enter a value for the form.',prediction={'code':'print(1)'})
    assert not loops_supported(unit)


def test_completed_session_surfaces_due_review_without_model_request(coach_browser):
    client,provider,_,app=coach_browser;course=practice(client)
    progress=private_progress(client,app,course);up=adaptive.unit_state(progress,course['unit']['id'])
    progress['complete']=True;up['independent_passed']=True;up['review_due_at']=time.time()-5;put_progress(client,app,course,progress)
    calls=len(provider.calls)+len(provider.research_calls)
    assert dashboard(client,course)['next_step']['kind']=='review_due'
    assert len(provider.calls)+len(provider.research_calls)==calls


def test_other_lesson_update_is_acknowledged_when_followup_is_opened(coach_browser):
    client,_,_,_=coach_browser;course=practice(client)
    response=client.post('/api/coach/research',json={'lesson_id':course['lesson_id'],'unit_id':course['unit']['id'],'consent':True})
    assert response.status_code==200
    result=finished(client,response.json()['research']['job']['id']);assert result['job']['status']=='ready'
    video=prepare(client,answer_lesson_checks=False)['learning']
    updates=dashboard(client,video)['updates'];assert any(x['lesson_id']==result['session']['lesson_id'] for x in updates)
    client.post('/api/coach/resume',json={'lesson_id':result['session']['lesson_id']})
    assert dashboard(client,course)['research']['opened']
    assert dashboard(client,course)['next_step']['kind']=='current_activity'
    assert not dashboard(client,video)['updates']


def test_previous_concept_permission_does_not_authorise_next_concept(coach_browser):
    client,provider,_,app=coach_browser;course=practice(client);permission(client,course)
    record=app.state.store.saved_lesson(who(client),course['lesson_id']);second=copy.deepcopy(record['curriculum']['units'][0]);second['id']='another-loop'
    record['curriculum']['units'].append(second);app.state.store.set_progress(who(client),'hub_session',record)
    progress=private_progress(client,app,course);progress['current_unit']=1;up=adaptive.unit_state(progress,second['id']);up['phase']='exercise'
    adaptive.active(up).update(failures=2,learner_expectation='I expected the outer loop to stop.')
    put_progress(client,app,course,progress);before=len(provider.research_calls)
    app.state.learning_coach.observe(who(client),record,progress)
    assert len(provider.research_calls)==before
    assert not dashboard(client,course)['research']['enabled'] and not dashboard(client,course)['research']['used']
