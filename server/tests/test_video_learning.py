"""Synthetic teaching fixtures; every execution assertion uses real WASI CPython."""
import asyncio
import copy
import json
import sys
import time
import uuid
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'))
from lessontrace_site.main import create_app
from lessontrace_site.runner import WasiRunner
from lessontrace_site import video_lessons


def fixture_quotes(evidence,source_ids):
    chunks=list(evidence.get('caption_chunks',[]))+list(evidence.get('caption_excerpts',[]))
    chunks += [chunk for source in evidence.get('reviewed_sources',[]) for chunk in source['chunks']]
    lookup={chunk['id']:chunk['text'] for chunk in chunks};result=[]
    for identifier in source_ids:
        quote=lookup[identifier][:175].rstrip()
        while len(quote.split())>25:quote=quote.rsplit(None,1)[0]
        result.append({'source_id':identifier,'claim':'The supplied passage describes this lesson concept.','quote':quote})
    return result


def lesson(source):
    return {'title':'Synthetic dictionary lesson','answer':'## Dictionary lookup\n\n'+('This synthetic test fixture explains looking up a value by its dictionary key. '*4),'sources':[source],
        'units':[{'id':'lookup','title':'Look up a value','explanation':'A dictionary connects each key with a value. Use the exact key to retrieve its value. This text is only a synthetic fixture.',
        'opening_question':'What does adding a new key change in this dictionary?','sources':[source],
        'quiz':[{'kind':'complete_code','prompt':'Complete this lookup so it prints Mia’s score.','code':'scores = {"Mia": 95, "Leo": 88}\nprint(scores___)','options':['["Mia"]','["Leo"]','["Ava"]'],'answer_index':0,'expected_output':'95','explanation':'The exact key Mia retrieves its associated score.','sources':[source]}],
        'prediction':{'prompt':'What will this program print?','code':'scores = {"Mia": 95, "Leo": 88}\nscores["Ava"] = 91\nprint(scores["Ava"])','options':['88','91','95'],'expected_output':'91','explanation':'The new Ava key is associated with 91.','sources':[source]},
        'exercise':{'title':'Find the named score','instructions':'Return the score for name, or 0 if it is missing. Keep the input dictionary unchanged.','entry':'score_for','starter':'def score_for(scores, name):\n    pass','reference_solution':'def score_for(scores, name):\n    return scores.get(name, 0)','preserve_input':True,
        'cases':[{'arguments':[{'Mia':95,'Leo':88},'Mia'],'expected':95},{'arguments':[{'Leo':88},'Leo'],'expected':88},{'arguments':[{},'Ava'],'expected':0}],'sources':[source]}}]}


class SyntheticMeta:
    enabled=True
    def __init__(self):self.calls=[];self.reviews=[];self.review_transform=None;self.invalid=False;self.always_invalid=False;self.action=None;self.variants=[];self.bad_variant=False
    async def generate(self,instruction,evidence,source_ids,**options):
        if evidence.get('review_task')=='claim-support-v1':
            self.reviews.append(copy.deepcopy(evidence));result=review_fixture(evidence)
            return self.review_transform(result) if self.review_transform else result
        self.calls.append(copy.deepcopy(evidence))
        if 'units' in options['schema'].get('properties',{}):
            result=lesson(source_ids[0])
            if self.always_invalid or (self.invalid and not evidence.get('repair_request')):result['units'][0]['prediction']['expected_output']='wrong'
        elif 'reference_solution' in options['schema'].get('properties',{}):
            n=len(self.variants)+1
            if evidence['kind']=='simpler':
                result={'title':'Read a single value','instructions':'Return the value under the key value, or 0 when absent. Do not change the input.','entry':'read_value','starter':'def read_value(record):\n    pass','reference_solution':'def read_value(record):\n    return record.get("value", 0)','preserve_input':True,
                    'cases':[{'arguments':[{'value':2}],'expected':2},{'arguments':[{}],'expected':0},{'arguments':[{'value':8}],'expected':8}],'sources':source_ids[:1]}
            else:
                result={'title':'Look up a new record','instructions':f'Return the requested key value, or {-n} when absent. Keep the input unchanged.','entry':f'lookup_{n}','starter':f'def lookup_{n}(record, key):\n    pass','reference_solution':f'def lookup_{n}(record, key):\n    return record.get(key, {-n})','preserve_input':True,
                    'cases':[{'arguments':[{'Ava':11+n},'Ava'],'expected':11+n},{'arguments':[{},'missing'],'expected':-n},{'arguments':[{'Leo':27+n},'Leo'],'expected':27+n}],'sources':source_ids[:1]}
            result['opening_question']='Which key does the task ask you to look up?'
            if self.bad_variant:result['cases'][0]['expected']=999
            self.variants.append(copy.deepcopy(result))
        elif 'quiz' in options['schema'].get('properties',{}):
            result={'quiz':lesson(source_ids[0])['units'][0]['quiz']}
            if self.invalid or self.always_invalid:result['quiz'][0]['expected_output']='wrong'
        else:
            actions=evidence.get('available_actions',['hint'])
            answers=['Notice the key passed to get.','Compare the requested name with the keys before selecting the fallback.','Follow the observed lookup step and distinguish the key from its value.']
            questions=['What value should a missing key return?','Which requested key is absent from this particular input?','How does the observed value compare with your expectation?','Which operation would you like to inspect next?']
            result={'answer':answers[min(evidence.get('help_level',0),2)],'follow_up':questions[min(evidence.get('help_level',0),3)],'sources':source_ids[:1],
                'action':self.action or ('hint' if 'hint' in actions else actions[0]),'reason':'The current attempt is available for a small teaching step.','source_id':source_ids[0],'trace_step':0}
        if 'evidence_quotes' in options['schema'].get('properties',{}):result['evidence_quotes']=fixture_quotes(evidence,source_ids)
        return result|{'provider':'meta','model':'synthetic-test-model'}


def review_fixture(payload):
    return {'request_hash':payload['request_hash'],'checks':[{'item_id':i['item_id'],'status':'supported','reason':'Controlled reviewer response for backend contract tests.','source_ids':[s['id'] for s in payload['sources']]} for i in payload['items']],
        'coverage':[{'criterion_id':c['id'],'status':'covered','item_id':payload['items'][0]['item_id'],'excerpt':payload['items'][0]['text'][:100]} for c in payload['required_coverage']],
        'provider':'meta','model':'synthetic-reviewer'}


@pytest.fixture
def browser(tmp_path,monkeypatch):
    captions={'origin':'Synthetic public-caption fixture','language':'en','is_generated':True,'snippets':[{'text':'Dictionary keys connect to values. Use get to choose a default.','start':0,'duration':20}]}
    monkeypatch.setattr(video_lessons,'fetch_captions',lambda *args:captions)
    runner=WasiRunner(tmp_path);runner.cache=ROOT/'.local'/'wasi-cache';asyncio.run(runner.warmup());assert runner.ready,runner.error
    provider=SyntheticMeta();app=create_app(tmp_path,runner=runner,provider=provider)
    with TestClient(app) as client:
        client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
        yield client,provider


def prepare(client,*,answer_lesson_checks=True):
    result=client.post('/api/video-session/learning',json={'url':'https://youtu.be/4t10v2QmTHU','consent':True})
    assert result.status_code==200,result.text
    data=result.json()
    if answer_lesson_checks:
        for question in data['learning']['unit']['quiz'][:-1]:
            checked=client.post('/api/video-learning/quiz',json=scope(data['learning'])|{'question_id':question['id'],'question_hash':question['question_hash'],'option':0})
            assert checked.status_code==200,checked.text
            data['learning']=checked.json()['learning']
    return data


def scope(course):return {'lesson_id':course['lesson_id'],'unit_id':course['unit']['id'],'activity_id':course['progress']['active_activity']}


def open_practice(client):
    course=prepare(client)['learning'];prediction=course['unit']['prediction']
    assert client.post('/api/video-learning/predict',json=scope(course)|{'source_hash':prediction['source_hash'],'option':1}).status_code==200
    return client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).json()['learning']


def fresh(client,course):
    response=client.post('/api/video-learning/move',json=scope(course)|{'action':'fresh_check','consent':True,'request_id':str(uuid.uuid4())})
    assert response.status_code==200,response.text
    return response.json()['learning']


def run(client,course,source,mode):
    result=client.post('/api/video-learning/run',json=scope(course)|{'source':source,'mode':mode})
    assert result.status_code==200,result.text
    for _ in range(250):
        saved=client.get('/api/runs/'+result.json()['id']).json()
        if saved['status'] in {'complete','failed','cancelled'}:return saved
        time.sleep(.02)
    raise AssertionError('Python run did not finish')


def test_generated_lesson_private_answers_real_execution_and_progress(browser):
    client,provider=browser;data=prepare(client);course=data['learning'];serialized=json.dumps(data)
    for secret in ['reference_solution','expected_output','answer_index','caption_chunks','curriculum','verification']:assert '"'+secret+'"' not in serialized
    assert 'reference_solution' not in client.get('/api/video-session').text
    assert 'reference_solution' not in client.get('/api/progress').text
    assert course['messages'][0]['role']=='assistant'
    gate=client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'});assert gate.status_code==409
    prediction=course['unit']['prediction']
    assert client.post('/api/video-learning/predict',json=scope(course)|{'source_hash':'0'*64,'option':1}).status_code==409
    assert not client.post('/api/video-learning/predict',json=scope(course)|{'source_hash':prediction['source_hash'],'option':0}).json()['correct']
    edited=prediction['code'].replace('91','92')
    assert client.post('/api/video-learning/run',json=scope(course)|{'source':edited,'mode':'prediction'}).status_code==409
    explored=run(client,course,edited,'explore');assert explored['report']['output']=='92\n' and not explored['report']['all_passed']
    assert client.get('/api/video-learning').json()['learning']['progress']['viewed_execution']
    assert client.post('/api/video-learning/predict',json=scope(course)|{'source_hash':prediction['source_hash'],'option':1}).json()['correct']
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).json()['learning']
    failed=run(client,course,course['unit']['exercise']['starter'],'exercise');assert not failed['report']['all_passed']
    good=run(client,course,'def score_for(scores, name):\n    return scores.get(name, 0)','exercise')
    assert good['status']=='complete' and good['report']['all_passed']
    assert good['report']['trace'] and good['report']['runtime'] and len(good['report']['checks'])==3
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).status_code==409
    course=fresh(client,course)
    independent=run(client,course,provider.variants[-1]['reference_solution'],'exercise')
    assert independent['report']['independent_check'] and not independent['report']['supported']
    done=client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).json()['learning'];assert done['progress']['complete']
    client.cookies.clear();client.get('/api/session');assert client.get('/api/video-learning').json()['learning'] is None


def test_meta_conversation_replies_have_trace_evidence_and_idempotency(browser):
    client,provider=browser;course=prepare(client)['learning'];source=course['unit']['prediction']['code'];checked=run(client,course,source,'prediction')
    body=scope(course)|{'text':'I think the new key adds one pair.','source':source,'consent':False,'request_id':str(uuid.uuid4()),'run_id':checked['id'],'step':2}
    assert client.post('/api/video-learning/coach',json=body).status_code==409
    body['consent']=True;result=client.post('/api/video-learning/coach',json=body);assert result.status_code==200,result.text
    messages=result.json()['learning']['messages'];assert [x['role'] for x in messages]==['assistant','user','assistant']
    assert messages[-1]['follow_up']=='What value should a missing key return?'
    assert provider.calls[-1]['checked'] and provider.calls[-1]['selected_step']
    assert provider.calls[-1]['previous_help_count']==0
    count=len(provider.calls);assert client.post('/api/video-learning/coach',json=body).status_code==200 and len(provider.calls)==count
    assert client.post('/api/video-learning/coach',json=body|{'text':'Changed reply'}).status_code==409
    body|={'request_id':str(uuid.uuid4()),'text':'It should return zero.'}
    assert client.post('/api/video-learning/coach',json=body).status_code==200
    assert provider.calls[-1]['recent_conversation'][-1]['follow_up']=='What value should a missing key return?'
    assert provider.calls[-1]['previous_help_count']==1
    assert client.post('/api/video-learning/coach',json=body|{'request_id':str(uuid.uuid4()),'source':source+'\nprint(0)'}).status_code==409
    assert client.post('/api/video-learning/coach',json=body|{'lesson_id':'0'*32}).status_code==409


def test_generation_repair_bounded_and_old_lesson_kept(browser):
    client,provider=browser;provider.invalid=True
    first=prepare(client);assert len(provider.calls)==2 and provider.calls[1]['repair_request']
    provider.always_invalid=True
    bad=client.post('/api/video-session/learning',json={'url':'https://youtu.be/4t10v2QmTHU','consent':True})
    assert bad.status_code==503 and len(provider.calls)==4
    assert client.get('/api/video-learning').json()['learning']['lesson_id']==first['learning']['lesson_id']


def test_no_consent_or_budget_means_no_model_call(browser):
    client,provider=browser
    assert client.post('/api/video-session/learning',json={'url':'https://youtu.be/4t10v2QmTHU','consent':False}).status_code==409
    assert not provider.calls
    course=prepare(client)['learning'];provider.action='review_source'
    generate=provider.generate
    async def budget_only(*args,**kwargs):
        result=await generate(*args,**kwargs)
        if not args[1].get('review_task'):result['follow_up']='Controlled allowance check '+str(len(provider.calls))
        return result
    provider.generate=budget_only
    body=scope(course)|{'text':'Please show the source rule.','source':course['unit']['prediction']['code'],'consent':True}
    for _ in range(4):assert client.post('/api/video-learning/coach',json=body|{'request_id':str(uuid.uuid4())}).status_code==200
    blocked=client.post('/api/video-learning/coach',json=body|{'request_id':str(uuid.uuid4())})
    assert blocked.status_code in {409,429} and len(provider.calls)==5 and len(provider.reviews)==5


def test_editor_styles_use_a_fresh_nonce_without_allowing_inline_scripts(browser):
    client,_=browser
    first=client.get('/');second=client.get('/')
    import re
    nonce=re.search(r'name="lessontrace-style-nonce" content="([^"]+)"',first.text).group(1)
    assert "'nonce-"+nonce+"'" in first.headers['content-security-policy']
    assert nonce not in second.text
    assert "script-src 'self';" in first.headers['content-security-policy']
    assert 'unsafe-inline' not in first.headers['content-security-policy']
    assert first.headers['cache-control']=='no-store'


def test_agent_asks_expectation_then_creates_a_checked_smaller_step(browser):
    client,provider=browser;course=open_practice(client)
    source='def score_for(scores, name):\n    return scores["missing"]'
    failed=run(client,course,source,'exercise');failed=run(client,course,source,'exercise')
    body=scope(course)|{'text':'Help me get unstuck.','source':source,'consent':True,'run_id':failed['id'],'request_id':str(uuid.uuid4()),'intent':'hint'}
    provider.action='simpler_practice'
    assert client.post('/api/video-learning/coach',json=body).status_code==503
    assert not provider.variants and 'simpler_practice' not in provider.calls[-1]['available_actions']
    provider.action='ask_expectation';body['request_id']=str(uuid.uuid4())
    question=client.post('/api/video-learning/coach',json=body);assert question.status_code==200,question.text
    assert question.json()['message']['action_result']['kind']=='ask_expectation'
    provider.action='simpler_practice';body|={'request_id':str(uuid.uuid4()),'intent':'reply','text':'I expected the score for the supplied name.'}
    easier=client.post('/api/video-learning/coach',json=body);assert easier.status_code==200,easier.text
    course=easier.json()['learning'];assert course['progress']['activity_kind']=='simpler'
    assert course['unit']['exercise']['instructions'] in easier.json()['message']['text']
    assert 'reference_solution' not in easier.text and 'variants' not in easier.text
    calls=len(provider.calls)
    assert client.post('/api/video-learning/coach',json=body).status_code==200 and len(provider.calls)==calls
    assert client.post('/api/video-learning/run',json=body|{'mode':'exercise'}).status_code==409
    checked=run(client,course,provider.variants[-1]['reference_solution'],'exercise')
    assert checked['report']['all_passed'] and not checked['report']['independent_check']
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'return_practice'}).json()['learning']
    assert course['progress']['active_activity']=='practice' and not course['progress']['practice_passed']


def test_help_on_fresh_task_is_supported_and_another_task_is_required(browser):
    client,provider=browser;course=open_practice(client)
    run(client,course,'def score_for(scores, name):\n    return scores.get(name, 0)','exercise')
    course=fresh(client,course);source=course['unit']['exercise']['starter'];failed=run(client,course,source,'exercise')
    request=scope(course)|{'text':'I expected a value. Please give me a hint.','source':source,'run_id':failed['id'],'consent':True,'request_id':str(uuid.uuid4()),'intent':'hint'}
    helped=client.post('/api/video-learning/coach',json=request);assert helped.status_code==200,helped.text
    checked=run(client,course,provider.variants[-1]['reference_solution'],'exercise')
    assert checked['report']['all_passed'] and checked['report']['supported'] and not checked['report']['independent_check']
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).status_code==409
    course=fresh(client,course);checked=run(client,course,provider.variants[-1]['reference_solution'],'exercise')
    assert checked['report']['independent_check']
    # Later help cannot retroactively change the fact that this run preceded help.
    request=scope(course)|{'text':'Can you explain why this worked?','source':checked['source'],'run_id':checked['id'],'consent':True,'request_id':str(uuid.uuid4())}
    assert client.post('/api/video-learning/coach',json=request).status_code==200
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).json()['learning']['progress']['complete']


def test_failed_variants_keep_current_work_and_transition_retry_does_not_spend(browser):
    client,provider=browser;course=open_practice(client)
    run(client,course,'def score_for(scores, name):\n    return scores.get(name, 0)','exercise')
    provider.bad_variant=True;body=scope(course)|{'action':'fresh_check','consent':True,'request_id':str(uuid.uuid4())}
    bad=client.post('/api/video-learning/move',json=body);assert bad.status_code==503,bad.text
    assert len(provider.variants)==2 and client.get('/api/video-learning').json()['learning']['progress']['active_activity']=='practice'
    provider.bad_variant=False;body['request_id']=str(uuid.uuid4())
    good=client.post('/api/video-learning/move',json=body);assert good.status_code==200,good.text
    calls=len(provider.calls);assert client.post('/api/video-learning/move',json=body).status_code==200 and len(provider.calls)==calls
    assert client.post('/api/video-learning/move',json=body|{'action':'review'}).status_code==409


def test_exploration_and_foreign_activity_trace_do_not_unlock_independent_check(browser):
    client,provider=browser;course=open_practice(client)
    old=run(client,course,'def score_for(scores, name):\n    return scores.get(name, 0)','exercise')
    course=fresh(client,course);explored=run(client,course,'print(5)','explore')
    assert not explored['report']['all_passed']
    assert not client.get('/api/video-learning').json()['learning']['progress']['independent_passed']
    body=scope(course)|{'source':old['source'],'run_id':old['id'],'text':'Explain this code.','consent':True,'request_id':str(uuid.uuid4())}
    assert client.post('/api/video-learning/coach',json=body).status_code==409
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).status_code==409


def test_later_review_uses_a_new_task_and_preserves_course_position(browser):
    client,provider=browser;course=open_practice(client)
    run(client,course,'def score_for(scores, name):\n    return scores.get(name, 0)','exercise')
    course=fresh(client,course);run(client,course,provider.variants[-1]['reference_solution'],'exercise')
    client.post('/api/video-learning/move',json=scope(course)|{'action':'next'})
    store=client.app.state.store;owner=hashlib.sha256(client.cookies['lessontrace_browser'].encode()).hexdigest()
    key='video_progress_'+course['lesson_id'];progress=store.progress(owner)[key]
    progress['units']['lookup']['review_due_at']=time.time()-1;store.set_progress(owner,key,progress)
    body=scope(course)|{'action':'review','review_unit_id':'lookup','consent':True,'request_id':str(uuid.uuid4())}
    review=client.post('/api/video-learning/move',json=body);assert review.status_code==200,review.text
    reviewed=review.json()['learning'];assert reviewed['progress']['reviewing'] and reviewed['progress']['activity_kind']=='review'
    result=run(client,reviewed,provider.variants[-1]['reference_solution'],'exercise');assert result['report']['independent_check']
    resumed=client.post('/api/video-learning/move',json=scope(reviewed)|{'action':'resume'}).json()['learning']
    assert resumed['progress']['complete'] and not resumed['progress']['reviewing']
    assert resumed['reviews'][0]['due_at']>time.time()


def test_legacy_completion_migrates_without_claiming_independence(browser):
    client,_=browser;course=open_practice(client)
    store=client.app.state.store;owner=hashlib.sha256(client.cookies['lessontrace_browser'].encode()).hexdigest();key='video_progress_'+course['lesson_id']
    progress=store.progress(owner)[key];progress.pop('adaptive_version',None);progress['complete']=True
    up=progress['units']['lookup'];up['practice_passed']=True;up['hint_count']=2
    for field in ['activities','variants','active_activity','independent_passed','review_due_at','attempt_history','decisions']:up.pop(field,None)
    store.set_progress(owner,key,progress)
    migrated=client.get('/api/video-learning').json()['learning']
    assert migrated['progress']['practice_passed'] and migrated['progress']['supported']
    assert not migrated['progress']['complete'] and not migrated['progress']['independent_passed']
    assert migrated['progress']['next_action']=='fresh_check'


def test_completing_last_concept_cannot_skip_missing_earlier_fresh_checks(browser):
    from lessontrace_site.video_learning import unit_progress
    client,_=browser;course=open_practice(client)
    store=client.app.state.store;owner=hashlib.sha256(client.cookies['lessontrace_browser'].encode()).hexdigest();key='video_progress_'+course['lesson_id']
    record=store.progress(owner)['youtube_session'];second=copy.deepcopy(record['curriculum']['units'][0]);second['id']='later-lookup'
    record['curriculum']['units'].append(second);store.set_progress(owner,'youtube_session',record)
    progress=store.progress(owner)[key];progress['current_unit']=1;unit_progress(progress,'later-lookup')['independent_passed']=True;store.set_progress(owner,key,progress)
    current=client.get('/api/video-learning').json()['learning']
    moved=client.post('/api/video-learning/move',json=scope(current)|{'action':'next'}).json()['learning']
    assert moved['unit_index']==0 and not moved['progress']['complete']


def test_meta_incomplete_response_has_safe_diagnostics():
    import httpx
    from lessontrace_site.meta import MetaProvider,MetaUnavailable
    def reply(request):return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"answer":'}}]})
    async def check():
        meta=MetaProvider(enabled=True,key='synthetic-test-key',transport=httpx.MockTransport(reply))
        with pytest.raises(MetaUnavailable,match='did not finish'):await meta.generate('Teach the concept.',{'sample':'synthetic'},['source'],max_completion_tokens=2600)
        assert meta.last_failure=={'kind':'incomplete','finish_reason':'length','max_completion_tokens':2600}
    asyncio.run(check())


def test_meta_schema_error_does_not_disclose_rejected_response_text():
    import httpx
    from lessontrace_site.meta import MetaProvider,MetaUnavailable
    rejected='synthetic-rejected-response-content'
    def reply(request):return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'answer':rejected})}}]})
    async def check():
        meta=MetaProvider(enabled=True,key='synthetic-test-key',transport=httpx.MockTransport(reply))
        with pytest.raises(MetaUnavailable) as error:await meta.generate('Teach the concept.',{},['source'])
        assert rejected not in str(error.value) and rejected not in json.dumps(meta.last_failure)
        assert meta.last_failure['kind']=='schema'
    asyncio.run(check())


def test_quiz_answers_are_private_scoped_and_formative(browser):
    client,_=browser;course=prepare(client,answer_lesson_checks=False)['learning'];questions=course['unit']['quiz']
    assert [q['kind'] for q in questions]==['complete_code','prediction']
    assert all('answer_index' not in q and 'expected_output' not in q and 'verification' not in q for q in questions)
    question=questions[0];body=scope(course)|{'question_id':question['id'],'question_hash':question['question_hash'],'option':1}
    assert client.post('/api/video-learning/quiz',json=body|{'question_hash':'0'*64}).status_code==409
    assert client.post('/api/video-learning/quiz',json=body|{'lesson_id':'0'*32}).status_code==409
    wrong=client.post('/api/video-learning/quiz',json=body).json();assert not wrong['correct'] and wrong['feedback']
    saved=client.get('/api/video-learning').json()['learning'];assert saved['progress']['quiz']['answered']==1
    assert not saved['progress']['quiz']['complete']
    question=questions[-1]
    result=client.post('/api/video-learning/quiz',json=scope(course)|{'question_id':question['id'],'question_hash':question['question_hash'],'option':0})
    assert result.status_code==200 and not result.json()['correct']
    progress=result.json()['learning']['progress'];assert progress['quiz']['complete'] and not progress['prediction_ok']
    # Completing a formative quiz permits practice even when answers need work.
    practiced=client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'}).json()['learning']
    assert practiced['progress']['phase']=='exercise' and not practiced['progress']['independent_passed']
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).status_code==409


def test_skip_quiz_persists_without_awarding_answers_or_bypassing_code(browser):
    client,provider=browser;course=prepare(client,answer_lesson_checks=False)['learning'];calls=len(provider.calls)
    skipped=client.post('/api/video-learning/move',json=scope(course)|{'action':'skip_quiz'});assert skipped.status_code==200
    course=client.get('/api/video-learning').json()['learning'];progress=course['progress']
    assert progress['phase']=='exercise' and progress['quiz']['skipped'] and progress['quiz']['answered']==0
    assert not progress['prediction_ok'] and not progress['practice_passed'] and not progress['independent_passed']
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'fresh_check','consent':True,'request_id':str(uuid.uuid4())}).status_code==409
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).status_code==409
    checked=run(client,course,'def score_for(scores, name):\n    return scores.get(name, 0)','exercise');assert checked['report']['all_passed']
    quiz=client.post('/api/video-learning/move',json=scope(course)|{'action':'quiz'}).json()['learning']
    assert quiz['progress']['phase']=='prediction' and quiz['progress']['practice_passed']
    reopened=client.post('/api/video-learning/move',json=scope(quiz)|{'action':'practice'}).json()['learning']
    assert reopened['progress']['last_run_id']==checked['id'] and not reopened['progress']['independent_passed']
    assert len(provider.calls)==calls


def test_quiz_skip_cannot_exit_a_fresh_or_review_activity(browser):
    client,_=browser;course=open_practice(client)
    run(client,course,'def score_for(scores, name):\n    return scores.get(name, 0)','exercise');course=fresh(client,course)
    for action in ['skip_quiz','quiz','practice']:
        assert client.post('/api/video-learning/move',json=scope(course)|{'action':action}).status_code==409
    assert client.get('/api/video-learning').json()['learning']['progress']['active_activity']==course['progress']['active_activity']


def legacy_quiz(client,course):
    store=client.app.state.store;owner=hashlib.sha256(client.cookies['lessontrace_browser'].encode()).hexdigest()
    record=store.progress(owner)['youtube_session'];record['curriculum']['units'][0].pop('quiz')
    store.set_progress(owner,'youtube_session',record)
    return store,owner,record


def test_saved_lesson_quiz_upgrade_is_consent_checked_bounded_and_idempotent(browser):
    client,provider=browser;course=prepare(client,answer_lesson_checks=False)['learning'];store,owner,record=legacy_quiz(client,course)
    legacy=client.get('/api/video-learning').json()['learning'];assert len(legacy['unit']['quiz'])==1
    body=scope(course)|{'consent':False,'request_id':str(uuid.uuid4())};calls=len(provider.calls)
    assert client.post('/api/video-learning/quiz/prepare',json=body).status_code==409 and len(provider.calls)==calls
    provider.invalid=True;body['consent']=True
    assert client.post('/api/video-learning/quiz/prepare',json=body).status_code==503
    assert len(provider.calls)==calls+2 and store.progress(owner)['youtube_session']==record
    provider.invalid=False;body['request_id']=str(uuid.uuid4())
    upgraded=client.post('/api/video-learning/quiz/prepare',json=body);assert upgraded.status_code==200,upgraded.text
    assert len(upgraded.json()['learning']['unit']['quiz'])==2 and upgraded.json()['learning']['progress']['quiz']['answered']==0
    saved=store.progress(owner)['youtube_session'];assert saved['lesson_id']==record['lesson_id'] and saved['answer']==record['answer']
    assert saved['curriculum']['units'][0]['exercise']==record['curriculum']['units'][0]['exercise']
    calls=len(provider.calls);assert client.post('/api/video-learning/quiz/prepare',json=body).status_code==200 and len(provider.calls)==calls


def test_quiz_generation_cannot_replace_a_newer_video_lesson(browser):
    client,provider=browser;course=prepare(client,answer_lesson_checks=False)['learning'];store,owner,record=legacy_quiz(client,course)
    original=provider.generate;newer=copy.deepcopy(record);newer['lesson_id']='a'*32
    async def replace(*args,**kwargs):
        result=await original(*args,**kwargs);store.set_progress(owner,'youtube_session',newer);return result
    provider.generate=replace
    result=client.post('/api/video-learning/quiz/prepare',json=scope(course)|{'consent':True,'request_id':str(uuid.uuid4())})
    assert result.status_code==409 and store.progress(owner)['youtube_session']==newer


def test_tutor_receives_current_quiz_context_without_private_answer(browser):
    client,provider=browser;course=prepare(client,answer_lesson_checks=False)['learning'];question=course['unit']['quiz'][0]
    body=scope(course)|{'text':'Can you give me a small hint for the blank?','source':course['unit']['prediction']['code'],'quiz_question_id':question['id'],'consent':True,'request_id':str(uuid.uuid4())}
    result=client.post('/api/video-learning/coach',json=body);assert result.status_code==200,result.text
    evidence=provider.calls[-1];assert evidence['quiz_question']['id']==question['id']
    assert evidence['quiz_question']['code'].endswith('print(scores___)') and 'answer_index' not in evidence['quiz_question']
    assert not evidence['quiz_progress']['complete']


@pytest.mark.parametrize('change',[{'answer_index':1},{'options':['["Mia"]','.get("Mia")','["Leo"]']}])
def test_code_completion_quiz_rejects_wrong_or_ambiguous_answer(browser,change):
    from lessontrace_site.video_curriculum import validate_quiz
    client,_=browser;question=lesson('video-fixture')['units'][0]['quiz'][0]|change
    with pytest.raises(ValueError,match='exactly one answer'):
        asyncio.run(validate_quiz([question],client.app.state.runner,['video-fixture']))


def concept_question(code='',prompt='Which item does friends[2] refer to?'):
    return {'kind':'concept','prompt':prompt,'code':code,'options':['The second item','The third item','The entire list'],
            'answer_index':1,'expected_output':'','explanation':'Indexing starts at zero, so index two identifies the third item.','sources':['video-fixture']}


@pytest.mark.parametrize('code',[
    'friends = ["Paul", \'Dana\', "Nathan"]',
    'first = "Paul"\nsecond = "Dana"\nthird = "Nathan"\nfriends = [first, second, third]',
])
def test_concept_context_accepts_quoted_strings_and_defined_variables(browser,code):
    from lessontrace_site.video_curriculum import validate_quiz
    client,_=browser
    question=asyncio.run(validate_quiz([concept_question(code)],client.app.state.runner,['video-fixture']))[0]
    assert question['code']==code and 'actual CPython' in question['verification']['basis']
    assert question['verification']['source_hash']==hashlib.sha256(code.encode()).hexdigest()


@pytest.mark.parametrize('code',['friends = [Paul, Dana, Nathan]','friends = ["Paul", missing_name, "Nathan"]'])
def test_concept_context_rejects_undefined_names_instead_of_assuming_strings(browser,code):
    from lessontrace_site.video_curriculum import validate_quiz
    client,_=browser
    with pytest.raises(ValueError,match='NameError.*Quote string literals'):
        asyncio.run(validate_quiz([concept_question(code)],client.app.state.runner,['video-fixture']))


@pytest.mark.parametrize('prompt',[
    'In friends = [Paul, Dana, Nathan], what does friends[2] give?',
    'In friends = ["Paul", "Dana", "Nathan"], what does friends[2] give?',
    'For [Paul, Dana, Nathan], which item is third?',
])
def test_quiz_premise_cannot_bypass_code_checks_by_hiding_inside_prose(browser,prompt):
    from lessontrace_site.video_curriculum import validate_quiz
    client,_=browser
    with pytest.raises(ValueError,match='code field'):
        asyncio.run(validate_quiz([concept_question(prompt=prompt)],client.app.state.runner,['video-fixture']))


def test_generation_repairs_an_unquoted_concept_example_before_saving(browser):
    client,provider=browser;original_generate=provider.generate
    async def generate(instruction,evidence,source_ids,**options):
        result=await original_generate(instruction,evidence,source_ids,**options)
        if 'units' in result:
            question=concept_question('friends = ["Paul", "Dana", "Nathan"]' if evidence.get('repair_request') else 'friends = [Paul, Dana, Nathan]')
            question['sources']=source_ids[:1];result['units'][0]['quiz']=[question]
        return result
    provider.generate=generate
    response=client.post('/api/video-session/learning',json={'url':'https://youtu.be/4t10v2QmTHU','consent':True})
    assert response.status_code==200,response.text
    assert len(provider.calls)==2 and 'NameError' in provider.calls[1]['repair_request']
    question=response.json()['learning']['unit']['quiz'][0]
    assert question['code']=='friends = ["Paul", "Dana", "Nathan"]' and 'answer_index' not in question
