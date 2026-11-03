"""Lesson-first progression: help is allowed; extra tasks are not a gate."""
import hashlib
import json
import uuid
from pathlib import Path

from test_course_workflow import course_browser,seed_known,open_topic,owner,answer_all,pass_concept
from test_video_learning import run,scope,fixture_quotes
from lessontrace_site.video_learning import progress_key


def test_prepared_foundation_is_a_teaching_lesson_and_saved_role_is_repaired(course_browser):
    client,_,app,_=course_browser;service=app.state.course_service
    artifact=json.loads((Path(__file__).resolve().parents[2]/'course_content/python-fundamentals-v2/variables.json').read_text(encoding='utf-8'))
    original=service.base;service.base=lambda concept:artifact if concept=='variables' else original(concept)
    opened=client.post('/api/course/open',json={'concept_id':'variables'});assert opened.status_code==200,opened.text
    session=opened.json()['session'];assert session['course_role']=='base' and session['course_flow']=='lesson-first'
    who=owner(client);record=app.state.store.saved_lesson(who,session['lesson_id']);before=app.state.store.progress(who)[progress_key(record['lesson_id'])]
    record.update(course_role='placement',caption_source='Original prerequisite assessment');app.state.store.save_lesson(who,record);app.state.store.set_progress(who,'course_session',record)
    restored=client.get('/api/course/session').json()['session'];assert restored['lesson_id']==session['lesson_id'] and restored['course_role']=='base'
    assert restored['caption_source']=='Frozen original course lesson with short source anchors'
    assert app.state.store.progress(who)[progress_key(record['lesson_id'])]==before


def use_teaching_flow(app):
    root=app.state.course_service.content_root;path=root/'for_loop.json';artifact=json.loads(path.read_text());artifact['flow']='lesson-first'
    raw=json.dumps(artifact).encode();path.write_bytes(raw);manifest=json.loads((root/'manifest.json').read_text());manifest['lessons']['for_loop']['sha256']=hashlib.sha256(raw).hexdigest();(root/'manifest.json').write_text(json.dumps(manifest))


def start_topic(client,app):
    use_teaching_flow(app);seed_known(client,app);course=open_topic(client,'for_loop')
    assert course['progress']['phase']=='lesson' and course['progress']['next_action']=='quiz'
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).status_code==409
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'quiz'}).json()['learning'];course=answer_all(client,app,course)
    return client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).json()['learning']


def test_lesson_then_topic_check_and_main_task_unlock_without_compulsory_fresh_task(course_browser):
    client,provider,app,_=course_browser;course=start_topic(client,app)
    record=app.state.store.progress(owner(client))['course_session'];reference=record['curriculum']['units'][0]['exercise']['reference_solution']
    assert client.post('/api/course/extra',json={'concept_id':'for_loop','lesson_id':course['lesson_id'],'consent':True}).status_code==409
    assert run(client,course,reference,'exercise')['report']['all_passed']
    current=client.get('/api/video-learning?context=course').json()['learning'];assert current['progress']['next_action']=='next'
    assert not current['progress']['independent_passed']
    board=client.get('/api/course').json();assert 'for_loop' in board['demonstrated']
    coach=client.get('/api/coach',params={'lesson_id':course['lesson_id']}).json();assert coach['current']['stage']=='complete' and coach['current']['complete']
    item=next(c for u in board['units'] for c in u['topics'] if c['id']=='for_loop');assert item['completion']['stage']=='complete' and not item['completion']['independent_required']
    moved=client.post('/api/video-learning/move',json=scope(current)|{'action':'next'});assert moved.status_code==200 and moved.json()['learning']['progress']['complete']
    assert not provider.calls


def test_meta_hint_keeps_the_current_task_and_does_not_require_extra_practice(course_browser):
    client,provider,app,_=course_browser;course=start_topic(client,app)
    for _ in range(2):run(client,course,'result = []','exercise')
    evidence=[]
    async def hint(instruction,context,source_ids,**kwargs):
        if context.get('review_task')=='claim-support-v1':
            from test_video_learning import review_fixture
            return review_fixture(context)
        evidence.append(context)
        return {'answer':'Follow how each supplied value contributes to the result list.','follow_up':'Which value should the first iteration place in the result?',
            'sources':source_ids[:1],'action':'hint','reason':'Offer a small step on the existing task.','source_id':source_ids[0],'trace_step':0,
            'evidence_quotes':fixture_quotes(context,source_ids),'provider':'meta','model':'controlled-test'}
    provider.enabled=True;provider.generate=hint
    response=client.post('/api/video-learning/coach',json=scope(course)|{'text':'I expected all input values in the result. Please give a small hint.','source':'result = []','consent':True,'intent':'hint','request_id':str(uuid.uuid4())})
    assert response.status_code==200,response.text
    assert not {'simpler_practice','fresh_check','research_topic'}&set(evidence[0]['available_actions'])
    assert response.json()['learning']['progress']['active_activity']=='practice'
    record=app.state.store.progress(owner(client))['course_session'];assert run(client,course,record['curriculum']['units'][0]['exercise']['reference_solution'],'exercise')['report']['all_passed']
    board=client.get('/api/course').json();assert board['evidence']['for_loop']['supported'] and 'for_loop' in board['demonstrated']


def test_old_checked_evidence_is_verified_and_earlier_attempts_stay_owned(course_browser):
    client,_,app,_=course_browser;pass_concept(client,app,'variables');open_topic(client,'arithmetic');store=app.state.store;who=owner(client);state=store.progress(who)['course_state']
    for identifier in state['lessons'].values():
        record=store.saved_lesson(who,identifier);record['course_version']='python-fundamentals-v1';store.save_lesson(who,record)
    state['version']='python-fundamentals-v1';state['evidence']['variables']['version']='python-fundamentals-v1';old_ids=dict(state['lessons']);store.set_progress(who,'course_state',state)
    board=client.get('/api/course').json();assert board['demonstrated']==['variables'] and len(board['earlier_lessons'])==2
    assert store.progress(who)['course_previous_python-fundamentals-v1']['lessons']==old_ids
    assert 'course_previous_' not in client.get('/api/progress').text
    for identifier in old_ids.values():assert store.saved_lesson(who,identifier)['course_version']=='python-fundamentals-v1'
    assert client.post('/api/course/earlier/open',json={'lesson_id':old_ids['arithmetic']}).status_code==200
    client.cookies.clear();client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
    assert client.post('/api/course/earlier/open',json={'lesson_id':old_ids['arithmetic']}).status_code==404
