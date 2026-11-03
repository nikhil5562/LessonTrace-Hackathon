"""Synthetic research decisions, real CPython checks, owned independent sessions."""
import asyncio
import copy
import hashlib
from io import BytesIO
import json
import time
import uuid
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from test_video_learning import ROOT,SyntheticMeta,prepare,run,scope,fixture_quotes
from lessontrace_site.main import create_app
from lessontrace_site.runner import WasiRunner
from lessontrace_site import video_lessons
from lessontrace_site.hub_sources import CATALOG
from lessontrace_site.hub import composition_schema
from jsonschema import validate as validate_json,ValidationError as SchemaError


def test_hub_schema_distinguishes_function_arguments_from_program_inputs():
    schema=composition_schema(['hub-python-0001'],[{'id':'python-control-flow'}])
    exercise=schema['$defs']['Exercise']|{'$defs':schema['$defs']}
    sample=loop_lesson(['hub-python-0001'])['units'][0]['exercise']
    validate_json(sample,exercise)
    with pytest.raises(SchemaError):validate_json(sample|{'parameters':['rows','limit']},exercise)
    with pytest.raises(SchemaError):validate_json(sample|{'kind':'program'},exercise)


def loop_lesson(sources):
    return {'title':'Follow the nearest loop','answer':'## One break, one loop\n\n'+('The break stops the inner loop; the outer loop can visit its next row. ' * 3)+'['+sources[0]+']\n\n## Added practice\n\nCompare the next outer iteration with the stopped inner iteration. ['+sources[-1]+']',
        'sources':sources,'units':[{'id':'nearest-loop','title':'Follow an inner break','explanation':'A break exits the nearest enclosing loop. An outer loop can then advance to its next item. Follow the two loop fingers separately and inspect the actual output. ['+sources[0]+']',
        'opening_question':'Which loop should advance after the first inner break?','sources':sources,
        'quiz':[{'kind':'concept','prompt':'Which loop does break leave?','code':'','options':['The nearest enclosing loop','Every enclosing loop','No loop'],'answer_index':0,'expected_output':'','explanation':'Break exits the nearest enclosing loop.','sources':sources[:1]}],
        'prediction':{'prompt':'What does this program print?','code':'for row in [[1, 2], [3, 4]]:\n    for value in row:\n        print(value)\n        break','options':['1\n3','1\n2\n3\n4','1'],'expected_output':'1\n3','explanation':'Each inner loop prints its first value then breaks; the outer loop advances.','sources':sources[:1]},
        'exercise':{'title':'Collect one match per row','instructions':'Return a list with the first value greater than limit from each row. Skip rows without a match. Do not change the input.','entry':'first_matches','starter':'def first_matches(rows, limit):\n    pass',
        'reference_solution':'def first_matches(rows, limit):\n    result = []\n    for row in rows:\n        for value in row:\n            if value > limit:\n                result.append(value)\n                break\n    return result','preserve_input':True,
        'cases':[{'arguments':[[[1, 7, 9], [8, 10]],5],'expected':[7,8]},{'arguments':[[[],[1,2]],5],'expected':[]},{'arguments':[[[3,4],[2,8]],3],'expected':[4,8]}],'sources':sources[:1]}}]}


class Sources:
    def __init__(self):self.calls=[];self.unavailable=set();self.delay=0
    async def read(self,identifier,focus,goal):
        self.calls.append(identifier)
        if self.delay:await asyncio.sleep(self.delay)
        if identifier in self.unavailable:raise ValueError('Synthetic source unavailable.')
        item=CATALOG[identifier];sid='hub-'+identifier+'-0001'
        return {'id':identifier,'title':item['title'],'kind':item['kind'],'url':item['url'],'fetched_at':1,'content_hash':'f'*64,'reviewed_sections':1,'available_sections':4,'coverage':'Selected synthetic excerpt only.',
            'chunks':[{'id':sid,'source_id':identifier,'source_title':item['title'],'kind':item['kind'],'url':item['url'],'start':10 if item['kind']=='video' else None,'end':20 if item['kind']=='video' else None,'heading':'Nearest loop','text':'A break exits the nearest enclosing loop. The outer loop can continue. This is a synthetic source fixture.','truncated':False}]}


class ResearchMeta(SyntheticMeta):
    def __init__(self):super().__init__();self.research_calls=[];self.second='inspect_example';self.bad_decision=False;self.bad_composition=False
    async def generate(self,instruction,evidence,source_ids,**options):
        props=options['schema'].get('properties',{})
        if 'source_ids' in props:
            self.research_calls.append(copy.deepcopy(evidence))
            if evidence['turn']==1:
                result={'action':'read_sources','source_ids':['python-control-flow','cs50-loops'],'reason':'Compare the primary reference with a worked teaching example.','example_code':''}
                if self.bad_decision:result['source_ids']=['python-control-flow','unread-site']
            else:
                action='read_sources' if len(evidence['reviewed_sources'])<2 else self.second
                result={'action':action,'source_ids':['learnpython-loops'] if action=='read_sources' else [],'reason':'Check which value is printed after the inner loop breaks.','example_code':'for row in [[1, 2], [3, 4]]:\n    for value in row:\n        print(value)\n        break' if action=='inspect_example' else ''}
        elif 'rationale' in props:
            self.research_calls.append(copy.deepcopy(evidence));sources=[c['id'] for s in evidence['reviewed_sources'] for c in s['chunks']]
            result={'lesson':loop_lesson(sources),'rationale':'Use the primary reference and the alternate explanation to follow one break at a time.','primary_source':'python-control-flow',
                'path':[{'title':'Follow the two loops','why':'Separate the inner and outer iterations before predicting output.','evidence_ids':sources[:1]},{'title':'Try a changed input','why':'Use a new row and inspect what happens after the first match.','evidence_ids':sources[-1:]}],
                'coverage':[{'concept':'Nearest enclosing loop','status':'supported','detail':'Both reviewed passages describe the scope of break.','evidence_ids':sources},{'concept':'Asynchronous iteration','status':'not_found','detail':'Not found in the selected excerpts; other sections were not reviewed.','evidence_ids':[]}],'differences':[]}
            if self.bad_composition:result['lesson']['units'][0]['prediction']['expected_output']='incorrect'
        elif 'reference_solution' in props:
            self.calls.append(copy.deepcopy(evidence));n=len(self.variants)+1
            result=copy.deepcopy(loop_lesson(source_ids)['units'][0]['exercise'])
            result.update(title='Find a smaller match per row',entry='smaller_matches_'+str(n),instructions='Return the first value below limit from each row, skipping rows without one. Do not change the input.',starter='def smaller_matches_'+str(n)+'(rows, limit):\n    pass',
                reference_solution='def smaller_matches_'+str(n)+'(rows, limit):\n    result = []\n    for row in rows:\n        for value in row:\n            if value < limit:\n                result.append(value)\n                break\n    return result',
                cases=[{'arguments':[[[8,1,2],[9,3]],4],'expected':[1,3]},{'arguments':[[[],[9,8]],4],'expected':[]},{'arguments':[[[2,1],[4,0]],2],'expected':[1,0]}],opening_question='Which comparison finds a value below the limit?')
            self.variants.append(copy.deepcopy(result))
        else:return await super().generate(instruction,evidence,source_ids,**options)
        if 'evidence_quotes' in props:result['evidence_quotes']=fixture_quotes(evidence,source_ids)
        return result|{'provider':'meta','model':'synthetic-research-model'}


@pytest.fixture
def hub_browser(tmp_path,monkeypatch):
    monkeypatch.setattr(video_lessons,'fetch_captions',lambda *a:{'origin':'Synthetic captions','language':'en','is_generated':False,'snippets':[{'text':'Dictionary keys and values.','start':0,'duration':20}]})
    runner=WasiRunner(tmp_path);runner.cache=ROOT/'.local/wasi-cache';asyncio.run(runner.warmup());assert runner.ready,runner.error
    provider=ResearchMeta();loader=Sources();app=create_app(tmp_path,runner=runner,provider=provider,hub_loader=loader)
    with TestClient(app) as client:
        client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
        yield client,provider,loader,app


def start(client,**changes):
    body={'goal':'I know a single loop, but I cannot predict an inner break.','focus':'nested-break','consent':True,'request_id':str(uuid.uuid4())}|changes
    response=client.post('/api/hub/research',json=body);assert response.status_code==200,response.text
    return body,response.json()


def finished(client,identifier):
    until=time.monotonic()+30
    while time.monotonic()<until:
        response=client.get('/api/hub/research/'+identifier);assert response.status_code==200,response.text
        result=response.json()
        if result['job']['status'] not in {'running','queued'}:return result
        time.sleep(.01)
    raise AssertionError('Synthetic Hub did not finish')


def ready(client,**changes):
    body,_=start(client,**changes);data=finished(client,body['request_id'])
    assert data['job']['status']=='ready',data
    return data


def test_research_tools_real_python_and_original_session_are_separate(hub_browser):
    client,provider,loader,_=hub_browser
    original=prepare(client,answer_lesson_checks=False);before=client.get('/api/video-learning').json()['learning']
    data=ready(client,base_lesson_id=before['lesson_id']);session=data['session']
    assert len(provider.research_calls)==3 and len(loader.calls)==2
    assert provider.research_calls[0]['current_lesson']['title']==before['unit']['title']
    actual=provider.research_calls[-1]['tool_observations'][0]['actual_execution']
    assert actual['output']=='1\n3\n' and actual['steps']>0 and actual['runtime']
    assert session['context']=='hub' and session['lesson_id']!=before['lesson_id']
    serialized=json.dumps(data)
    for secret in ['reference_solution','answer_index','expected_output','caption_chunks','curriculum','input_hash']:
        assert '"'+secret+'"' not in serialized
    assert 'hub_session' not in client.get('/api/progress').text
    assert client.get('/api/video-learning').json()['learning']==before
    assert client.get('/api/video-session').json()['session']==original['session']
    course=client.get('/api/video-learning?context=hub').json()['learning'];assert course['context']=='hub'
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'skip_quiz'}).json()['learning']
    failed=run(client,course,course['unit']['exercise']['starter'],'exercise');assert not failed['report']['all_passed']
    source=loop_lesson(session['sources'])['units'][0]['exercise']['reference_solution']
    passed=run(client,course,source,'exercise');assert passed['report']['all_passed'] and len(passed['report']['checks'])==3
    assert client.post('/api/video-learning/move',json=scope(course)|{'action':'next'}).status_code==409
    old_trace=run(client,before,before['unit']['prediction']['code'],'prediction')
    cross=client.post('/api/video-learning/coach',json=scope(course)|{'text':'Explain this trace','source':old_trace['source'],'run_id':old_trace['id'],'consent':True,'request_id':str(uuid.uuid4())})
    assert cross.status_code==409
    provider.action='review_source'
    reply=client.post('/api/video-learning/coach',json=scope(course)|{'text':'Explain the inner break.','source':source,'run_id':passed['id'],'consent':True,'request_id':str(uuid.uuid4())})
    assert reply.status_code==200,reply.text
    assert reply.json()['message']['action_result']['source_id'].startswith('hub-')
    assert client.get('/api/video-learning').json()['learning']['progress']['hint_count']==0


def test_requests_are_idempotent_owned_and_require_consent_and_budget(hub_browser):
    client,provider,loader,app=hub_browser
    body={'goal':'Explain the nearest loop and inner break','request_id':str(uuid.uuid4())}
    assert client.post('/api/hub/research',json=body).status_code==409
    app.state.store.provider_limit_cents=30
    assert client.post('/api/hub/research',json=body|{'consent':True}).status_code==409
    assert provider.research_calls==[]
    app.state.store.provider_limit_cents=100;loader.delay=.08
    body,data=start(client);duplicate=client.post('/api/hub/research',json=body)
    assert duplicate.status_code==200 and duplicate.json()['job']['id']==body['request_id']
    assert client.post('/api/hub/research',json=body|{'goal':'A different goal about loops'}).status_code==409
    done=finished(client,body['request_id']);assert done['job']['status']=='ready'
    assert len(provider.research_calls)==3
    count=len(provider.research_calls);assert client.post('/api/hub/research',json=body).status_code==200
    assert len(provider.research_calls)==count
    client.cookies.clear();new=client.get('/api/session').json()
    assert client.get('/api/hub').json()['session'] is None
    assert client.get('/api/hub/research/'+body['request_id']).status_code==404
    assert client.get('/api/video-learning?context=hub').json()['learning'] is None
    assert client.post('/api/hub/research',json=body).status_code==403
    client.headers['X-LessonTrace-CSRF']=new['csrf']
    assert client.post('/api/hub/research',json=body|{'base_lesson_id':done['session']['lesson_id']}).status_code==409


def test_hub_fresh_check_uses_the_same_independence_gate(hub_browser):
    client,provider,_,_=hub_browser;original=prepare(client,answer_lesson_checks=False)
    data=ready(client);course=client.get('/api/video-learning?context=hub').json()['learning']
    course=client.post('/api/video-learning/move',json=scope(course)|{'action':'skip_quiz'}).json()['learning']
    source=loop_lesson(data['session']['sources'])['units'][0]['exercise']['reference_solution']
    assert run(client,course,source,'exercise')['report']['all_passed']
    fresh=client.post('/api/video-learning/move',json=scope(course)|{'action':'fresh_check','consent':True,'request_id':str(uuid.uuid4())})
    assert fresh.status_code==200,fresh.text
    course=fresh.json()['learning'];assert course['progress']['activity_kind']=='fresh'
    actual=run(client,course,provider.variants[-1]['reference_solution'],'exercise')
    assert actual['report']['independent_check'] and not actual['report']['supported']
    done=client.post('/api/video-learning/move',json=scope(course)|{'action':'next','request_id':str(uuid.uuid4())})
    assert done.status_code==200 and done.json()['learning']['progress']['complete']
    assert done.json()['learning']['reviews']
    assert client.get('/api/video-session').json()['session']==original['session']


def test_cancel_and_interrupted_job_keep_previous_lessons(hub_browser):
    client,provider,loader,app=hub_browser;previous=ready(client)['session']
    loader.delay=30;body,_=start(client)
    until=time.monotonic()+3
    while len(loader.calls)<4 and time.monotonic()<until:time.sleep(.01)
    stopped=client.post('/api/hub/research/'+body['request_id']+'/cancel',json={})
    assert stopped.status_code==200 and stopped.json()['job']['status']=='cancelled'
    assert client.get('/api/hub').json()['session']==previous
    assert client.get('/api/video-learning?context=hub').json()['learning']['lesson_id']==previous['lesson_id']
    who=hashlib.sha256(client.cookies.get('lessontrace_browser').encode()).hexdigest();identifier=str(uuid.uuid4())
    app.state.store.set_progress(who,'hub_job_'+identifier,{'id':identifier,'status':'running','phase':'reading','message':'interrupted','steps':[],'created':time.time()+1,'updated':time.time()})
    state=client.get('/api/hub').json();assert state['job']['status']=='failed' and state['job']['phase']=='interrupted'
    assert state['session']==previous


def test_deleting_browser_data_stops_research_without_resetting_allowance(hub_browser):
    client,provider,loader,app=hub_browser;loader.delay=30
    body,_=start(client);until=time.monotonic()+3
    while not loader.calls and time.monotonic()<until:time.sleep(.01)
    before=app.state.store.provider_allowance()['reserved_cents']
    assert client.delete('/api/my-data').status_code==200
    client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
    assert client.get('/api/hub').json()['session'] is None
    assert client.get('/api/hub/research/'+body['request_id']).status_code==404
    assert app.state.store.provider_allowance()['reserved_cents']==before and before>0


@pytest.mark.parametrize('failure',['decision','sources','official','composition'])
def test_invalid_or_unavailable_research_never_publishes_a_lesson(hub_browser,failure):
    client,provider,loader,_=hub_browser
    if failure=='decision':provider.bad_decision=True
    if failure=='sources':loader.unavailable={'python-control-flow','cs50-loops'}
    if failure=='official':loader.unavailable={'python-control-flow'}
    if failure=='composition':provider.bad_composition=True
    body,_=start(client);data=finished(client,body['request_id'])
    assert data['job']['status']=='failed' and data['session'] is None
    assert client.get('/api/hub').json()['session'] is None
    assert len(provider.research_calls)<=(4 if failure=='composition' else 2)
    if failure=='composition':assert provider.research_calls[-1]['repair_request']


def test_source_aware_downloads_revisions_and_ownership(hub_browser):
    client,_,_,_=hub_browser;data=ready(client);session=data['session']
    base='/api/video-session/download/'
    args='?context=hub&expected_revision='+session['revision']
    text=client.get(base+'md'+args);assert text.status_code==200
    assert 'https://docs.python.org/3/tutorial/controlflow.html' in text.text
    assert 'https://www.youtube.com/watch?v=-7xg8pGcP6w' in text.text
    assert '[hub-' not in text.text and 'selected passages' in text.text
    doc=client.get(base+'docx'+args);assert doc.status_code==200
    with ZipFile(BytesIO(doc.content)) as archive:
        relations=archive.read('word/_rels/document.xml.rels').decode();assert 'docs.python.org' in relations and 'youtube.com' in relations
    pdf=client.get(base+'pdf'+args);assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    assert client.get(base+'md?context=hub&expected_revision='+'0'*64).status_code==409
    assert client.get(base+'md?expected_revision='+session['revision']).status_code==404
    client.cookies.clear();client.get('/api/session');assert client.get(base+'md'+args).status_code==404


def test_failed_preparation_reuses_passages_under_the_remaining_allowance(hub_browser):
    client,provider,loader,app=hub_browser;provider.bad_composition=True
    body,_=start(client);failure=finished(client,body['request_id']);assert failure['job']['can_retry']
    assert 'checkpoint' not in json.dumps(failure)
    before=app.state.store.provider_allowance()['reserved_cents'];assert before==40
    app.state.store.provider_limit_cents=80
    assert client.post('/api/hub/research/'+body['request_id']+'/retry',json={'consent':False}).status_code==409
    provider.bad_composition=False
    response=client.post('/api/hub/research/'+body['request_id']+'/retry',json={'consent':True});assert response.status_code==200,response.text
    result=finished(client,body['request_id']);assert result['job']['status']=='ready' and not result['job']['can_retry']
    assert len(loader.calls)==2 and len(provider.research_calls)==5
    assert provider.research_calls[-1]['allowed_passage_ids']
    assert app.state.store.provider_allowance()['reserved_cents']==60
    assert client.post('/api/hub/research/'+body['request_id']+'/retry',json={'consent':True}).status_code==409


@pytest.mark.parametrize('fault',['foreign_array','foreign_inline','persistent_foreign','provider_unavailable'])
def test_fresh_variant_cites_only_retrieved_passages_and_repairs_boundedly(hub_browser,fault):
    import httpx
    from lessontrace_site import adaptive
    from lessontrace_site.meta import MetaProvider,MetaUnavailable
    from lessontrace_site.video_learning import blank_progress
    _,_,_,app=hub_browser
    allowed='hub-python-control-flow-0001';omitted='hub-cs50-loops-0001'
    unit=loop_lesson([allowed,omitted])['units'][0]
    progress=blank_progress({'curriculum':{'units':[unit]}});up=adaptive.unit_state(progress,unit['id'])
    baseline=copy.deepcopy(up);requests=[];reservations=[]
    def respond(request):
        wire=json.loads(request.content);evidence=json.loads(wire['messages'][1]['content'][0]['text']);requests.append(evidence)
        assert wire['response_format']['json_schema']['schema']['properties']['sources']['items']['enum']==[allowed]
        assert evidence['allowed_passage_ids']==[allowed]
        if fault=='provider_unavailable':return httpx.Response(503)
        result=copy.deepcopy(unit['exercise'])
        result.update(title='First smaller value in each row',instructions='Return the first value below limit from each row, skipping rows without a match. Keep rows unchanged.',entry='first_smaller',
            starter='def first_smaller(rows, limit):\n    pass',
            reference_solution='def first_smaller(rows, limit):\n    result = []\n    for row in rows:\n        for value in row:\n            if value < limit:\n                result.append(value)\n                break\n    return result',
            cases=[{'arguments':[[[8,1,2],[9,3]],4],'expected':[1,3]},{'arguments':[[[],[9,8]],4],'expected':[]},{'arguments':[[[2,1],[4,0]],2],'expected':[1,0]}],
            sources=[allowed],opening_question='What should happen to a row with no smaller value?')
        result['evidence_quotes']=fixture_quotes(evidence,[allowed])
        if fault=='persistent_foreign' or len(requests)==1:
            if fault=='foreign_inline':result['instructions']+=' ['+omitted+']'
            else:result['sources']=[omitted]
        return httpx.Response(200,json={'model':'synthetic-wire-fixture','choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]})
    meta=MetaProvider(enabled=True,key='synthetic-test-key',transport=httpx.MockTransport(respond))
    async def check():
        return await adaptive.make_variant(meta,app.state.runner,asyncio.Semaphore(1),lambda *args:reservations.append(args),'synthetic-owner',unit,up,
            [{'id':allowed,'start':None,'end':None,'text':'A break exits the nearest enclosing loop; the outer loop can continue.'}],'fresh')
    if fault=='provider_unavailable':
        with pytest.raises(MetaUnavailable):asyncio.run(check())
        assert len(requests)==len(reservations)==1
    elif fault=='persistent_foreign':
        with pytest.raises(ValueError,match='Existing work was kept'):asyncio.run(check())
        assert len(requests)==len(reservations)==2
    else:
        result=asyncio.run(check());assert result['exercise']['sources']==[allowed]
        assert len(requests)==len(reservations)==2 and requests[-1]['repair_request']
    assert up==baseline,'Preparing or rejecting a task must not mutate the current activity.'
