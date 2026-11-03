"""Real-runtime acceptance checks for the new guided learning slice."""
import asyncio
import json
import time
from pathlib import Path
import sys
import pytest
import httpx
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'))
from lessontrace_site.runner import WasiRunner
from lessontrace_site.main import create_app
from lessontrace_site.learning_content import TASKS,TOPICS
from lessontrace_site.learning import learning_state
from lessontrace_site.meta import MetaProvider, MetaUnavailable


@pytest.fixture(scope='module')
def learning_runtime(tmp_path_factory):
    runner=WasiRunner(tmp_path_factory.mktemp('learning-runtime'))
    runner.cache=ROOT/'.local'/'wasi-cache'
    asyncio.run(runner.warmup())
    assert runner.ready,runner.error
    yield runner
    asyncio.run(runner.close())


@pytest.fixture
def browser(tmp_path):
    runner=WasiRunner(tmp_path)
    runner.cache=ROOT/'.local'/'wasi-cache'
    asyncio.run(runner.warmup())
    assert runner.ready
    app=create_app(tmp_path,runner=runner,provider=MetaProvider(enabled=False))
    with TestClient(app) as client:
        client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
        yield client


def wait(client,started):
    assert started.status_code==200,started.text
    identifier=started.json()['id']
    for _ in range(200):
        run=client.get('/api/runs/'+identifier).json()
        if run['status'] in {'complete','failed','cancelled'}:
            return run
        time.sleep(.02)
    raise AssertionError('Run did not finish')


def predict(client,topic):
    question=client.get('/api/learning/'+topic).json()['question']
    original=next(q for q in TOPICS[topic]['prediction'] if q['id']==question['id'])
    return client.post('/api/learning/'+topic+'/predict',json={'question_id':question['id'],'answer':original['answer']})


@pytest.mark.parametrize('task_id',list(TASKS))
def test_every_authored_oracle_with_actual_python(learning_runtime,task_id):
    task=TASKS[task_id]
    raw=asyncio.run(learning_runtime.execute({'source':task['solution'],'entry':task['entry'],'arguments':[c['args'] for c in task['cases']],'trace_case':0}))
    assert 'error' not in raw,raw
    assert [c.get('actual') for c in raw['cases']]==[c['expected'] for c in task['cases']],raw
    assert all(not c.get('error') for c in raw['cases'])


def test_real_keyerror_and_corrected_lookup(learning_runtime):
    task=TASKS['airport-label']
    raw=asyncio.run(learning_runtime.execute({'source':task['starter'],'entry':task['entry'],'arguments':[task['cases'][0]['args']],'trace_case':0}))
    case=raw['cases'][0]
    assert case['error']['type']=='KeyError'
    assert any(e.get('error',{}).get('type')=='KeyError' for e in case['events'])
    objects=[o for e in case['events'] for o in e['objects'].values()]
    assert any(o['type']=='dict' and any(p['key'].get('value')=='city' for p in o['entries']) for o in objects)


def test_inner_break_does_not_end_outer_loop_or_rewrite_prior_events(learning_runtime):
    source=TOPICS['nested']['example']
    raw=asyncio.run(learning_runtime.execute({'source':source,'entry':None,'arguments':[[]],'trace_case':0}))
    case=raw['cases'][0]
    assert case['output']=='found torch\nmissing map\n'
    events=case['events']
    broken=next(e for e in events if e.get('control',{}).get('action')=='break')
    assert broken['control']['loop_line']==4
    assert any(l.get('broken') for l in broken['loops'] if l['line']==4)
    before=[e for e in events[:broken['step']] if any(l['line']==4 for l in e['loops'])]
    assert before and not any(l.get('broken') for e in before for l in e['loops'])
    assert any(l['line']==3 and l['index']==1 for e in events[broken['step']+1:] for l in e['loops'])


def test_items_unpacking_mutation_and_popitem(learning_runtime):
    source='groups = {"A": [1], "B": [2]}\nfor name, values in groups.items():\n    values.append(3)\nprint(groups)\ncountry, price = groups.popitem()\nprint(country, price)\n'
    raw=asyncio.run(learning_runtime.execute({'source':source,'entry':None,'arguments':[[]],'trace_case':0}))
    case=raw['cases'][0]
    assert not case.get('error'),case
    assert case['output']=="{'A': [1, 3], 'B': [2, 3]}\nB [2, 3]\n"
    final=case['events'][-1]
    bindings=final['frames'][-1]['bindings']
    assert bindings['price']['object_id']==bindings['values']['object_id']


def test_dictionary_addition_pop_default_and_recorded_states(learning_runtime):
    source='scores = {"Mia": 95, "Leo": 88}\nscores["Ava"] = 91\nremoved = scores.pop("Leo")\nfallback = scores.pop("missing", 0)\nfor name, score in scores.items():\n    print(name, score)\nprint(removed, fallback)\n'
    raw=asyncio.run(learning_runtime.execute({'source':source,'entry':None,'arguments':[[]],'trace_case':0}))
    case=raw['cases'][0]
    assert not case.get('error'),case
    assert case['output']=='Mia 95\nAva 91\n88 0\n'
    states=[o for e in case['events'] for o in e['objects'].values() if o['type']=='dict']
    assert any(any(p['key'].get('value')=='Leo' for p in o['entries']) for o in states)
    assert [p['key']['value'] for p in states[-1]['entries']]==['Mia','Ava']


def test_dictionary_pop_missing_key_keeps_actual_exception(learning_runtime):
    raw=asyncio.run(learning_runtime.execute({'source':'values = {"present": 1}\nvalues.pop("absent")\n','entry':None,'arguments':[[]],'trace_case':0}))
    case=raw['cases'][0]
    assert case['error']['type']=='KeyError' and 'absent' in case['error']['message']


def test_no_stage_skip_and_prediction_feedback(browser):
    task=TASKS['count-parcels']
    assert browser.post('/api/learning/attempt',json={'task_id':task['id'],'source':task['solution']}).status_code==409
    question=browser.get('/api/learning/counting').json()['question']
    wrong=browser.post('/api/learning/counting/predict',json={'question_id':question['id'],'answer':'67'}).json()
    assert wrong['correct'] is False and 'total' in wrong['feedback']
    assert wrong['state']['next_task']['id']=='count-rain'
    assert predict(browser,'counting').json()['correct'] is True
    assert browser.post('/api/learning/attempt',json={'task_id':task['id'],'source':task['solution']}).status_code==409


def test_supported_attempts_need_fresh_independent_transfer(browser):
    predict(browser,'counting')
    for identifier in ['count-rain','count-parcels']:
        task=TASKS[identifier]
        result=wait(browser,browser.post('/api/learning/attempt',json={'task_id':identifier,'source':task['solution'],'origin':'qa_walkthrough'}))
        assert result['report']['all_passed'],result
    task=TASKS['sum-readings']
    browser.post('/api/learning/counting/coach',json={'task_id':task['id'],'question':'Give me a hint','source':task['starter']})
    result=wait(browser,browser.post('/api/learning/attempt',json={'task_id':task['id'],'source':task['solution']}))
    assert result['report']['all_passed'] and result['report']['assisted_before']
    state=browser.get('/api/learning/counting').json()
    assert not state['complete'] and state['next_task']['id']=='sum-scores'
    task=TASKS['sum-scores']
    wait(browser,browser.post('/api/learning/attempt',json={'task_id':task['id'],'source':task['solution']}))
    state=browser.get('/api/learning/counting').json()
    assert state['complete'] and state['review_due_at']>time.time()
    assert state['steps'][-1]['status']=='independent checks passed'


def test_coach_rejects_stale_and_other_browser_runs(browser):
    predict(browser,'dictionary')
    task=TASKS['airport-label']
    run=wait(browser,browser.post('/api/learning/attempt',json={'task_id':task['id'],'source':task['starter']}))
    body={'task_id':task['id'],'question':'Why this step?','source':task['solution'],'run_id':run['id']}
    assert browser.post('/api/learning/dictionary/coach',json=body).status_code==409
    body['source']=task['starter']
    assert browser.post('/api/learning/dictionary/coach',json=body).status_code==200
    browser.cookies.clear()
    browser.headers['X-LessonTrace-CSRF']=browser.get('/api/session').json()['csrf']
    assert browser.post('/api/learning/dictionary/coach',json=body).status_code==409
    assert browser.get('/api/learning/dictionary').json()['messages']==[]


def test_source_attachment_does_not_fetch_arbitrary_urls(browser):
    assert browser.post('/api/learning/counting/source',json={'url':'http://127.0.0.1:8765/private','notes':'secret','reviewed':True}).status_code==422
    link='https://youtu.be/fz_BCnhEQYQ?si=example'
    assert browser.post('/api/learning/counting/source',json={'url':link,'notes':'A function returns a value.'}).status_code==409
    result=browser.post('/api/learning/counting/source',json={'url':link,'notes':'A function returns a value.','reviewed':True}).json()
    assert result['source']['video_id']=='fz_BCnhEQYQ'
    assert 'no automatic full-video analysis' in result['source']['coverage'].lower()


def test_no_meta_request_without_consent(browser):
    task=TASKS['count-rain']
    result=browser.post('/api/learning/counting/coach',json={'task_id':task['id'],'question':'Hint','source':task['starter'],'provider':'meta','consent':False})
    assert result.status_code==409
    with browser.app.state.store.db() as db:
        assert db.execute('SELECT count(*) FROM provider_reservations').fetchone()[0]==0


def test_dictionary_task_cannot_mutate_input_to_fake_answer(browser):
    predict(browser,'dictionary')
    task=TASKS['airport-label']
    source='def airport_label(locations, code):\n    selected = locations[code]\n    answer = selected["city"] + " - " + selected["country"]\n    selected["city"] = "changed"\n    return answer\n'
    run=wait(browser,browser.post('/api/learning/attempt',json={'task_id':task['id'],'source':source}))
    assert not run['report']['all_passed']
    assert all(not c['input_unchanged'] for c in run['report']['checks'])


def test_real_exploration_is_not_counted_as_task_completion(browser):
    raw=wait(browser,browser.post('/api/learning/explore',json={'source':'a = {"city": "London"}\nprint(a["city"])\n'}))
    assert raw['report']['output']=='London\n'
    assert raw['report']['checks']==[] and not raw['report']['all_passed']
    state=browser.get('/api/learning/dictionary').json()
    assert not state['complete'] and not state['attempts']


def test_exploration_still_blocks_host_access_and_private_names(browser):
    for source in ['import os\nprint(os.getcwd())','x = {}\nprint(x.__class__)','print(open("file"))']:
        assert browser.post('/api/learning/explore',json={'source':source}).status_code==422


def test_enabled_meta_requires_consent_and_receives_bounded_followup_context(tmp_path):
    sent=[]
    def respond(request):
        payload=json.loads(request.content)
        evidence=json.loads(payload['messages'][-1]['content'][0]['text'])
        sent.append(evidence)
        assert evidence['code_checked'] is False and evidence['observed_checks']==[]
        assert evidence['recent_conversation'][0]['question']=='What does return do?'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'answer':'Return sends a value to the caller. What will your function return on empty input?','sources':['function-return']})}}]})
    class IdleRunner:
        ready,error=True,None
        async def warmup(self): pass
        async def close(self): pass
    provider=MetaProvider(enabled=True,key='synthetic-not-a-real-key',transport=httpx.MockTransport(respond))
    with TestClient(create_app(tmp_path,runner=IdleRunner(),provider=provider)) as client:
        client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
        body={'task_id':'count-rain','question':'What does return do?','source':TASKS['count-rain']['starter']}
        assert client.post('/api/learning/counting/coach',json=body).status_code==200
        body.update(question='I still do not understand that.',provider='meta',consent=False)
        assert client.post('/api/learning/counting/coach',json=body).status_code==409 and not sent
        body['consent']=True
        result=client.post('/api/learning/counting/coach',json=body)
        assert result.status_code==200,result.text
        assert len(sent)==1 and result.json()['allowance']['remaining_requests']==9


def test_keyerror_does_not_claim_unobserved_input_mutation(browser):
    predict(browser,'dictionary')
    task=TASKS['airport-label']
    result=wait(browser,browser.post('/api/learning/attempt',json={'task_id':task['id'],'source':task['starter']}))
    assert result['report']['checks'][0]['error']['type']=='KeyError'
    assert result['report']['checks'][0]['input_unchanged'] is None


def test_large_meta_context_is_rejected_without_sending():
    calls=[]
    provider=MetaProvider(enabled=True,key='synthetic',transport=httpx.MockTransport(lambda request:calls.append(request)))
    with pytest.raises(MetaUnavailable,match='too large'):
        asyncio.run(provider.generate('Explain',{'text':'x'*25000},['source-1']))
    assert not calls
