"""Original demo uses real Python, preserves the course, and never fakes Meta calls."""
import asyncio
import hashlib
import time

import pytest
from fastapi.testclient import TestClient
from lessontrace_site.main import create_app
from lessontrace_site.runner import WasiRunner,ROOT
from lessontrace_site.judge_demo import STARTER,REFERENCE,PREDICTION,SOURCE
from test_video_learning import scope,run


class NoCloud:
    enabled=False
    async def generate(self,*args,**kwargs):raise AssertionError('Prepared original demo must not call a model')


@pytest.fixture
def demo_client(tmp_path):
    runner=WasiRunner(tmp_path);runner.cache=ROOT/'.local/wasi-cache'
    asyncio.run(runner.warmup());assert runner.ready,runner.error
    app=create_app(tmp_path,runner=runner,provider=NoCloud())
    with TestClient(app) as client:
        client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
        yield client,app


def test_original_demo_is_keyless_and_does_not_award_course_evidence(demo_client):
    client,app=demo_client
    before=client.get('/api/course').json()
    assert client.post('/api/demo/start',headers={'X-LessonTrace-CSRF':'wrong'}).status_code==403
    response=client.post('/api/demo/start');assert response.status_code==200,response.text
    record=response.json()['session'];assert record['original_demo'] and record['provider']=='prepared-original'
    assert record['model'] is None and not any(d['kind']=='video' for d in record['source_documents'])
    assert client.get('/demo/source.txt').text==SOURCE
    course=client.get('/api/video-learning?context=hub').json()['learning']
    unit=app.state.store.progress(hashlib.sha256(client.cookies['lessontrace_browser'].encode()).hexdigest())['hub_session']['curriculum']['units'][0]
    for public,private in zip(course['unit']['quiz'],unit['quiz']+[unit['prediction']]):
        response=client.post('/api/video-learning/quiz',json=scope(course)|{'question_id':public['id'],'question_hash':public['question_hash'],'option':private['answer_index']})
        assert response.status_code==200,response.text;course=response.json()['learning']
    response=client.post('/api/video-learning/move',json=scope(course)|{'action':'practice'})
    assert response.status_code==200,response.text;course=response.json()['learning']
    failed=run(client,course,STARTER,'exercise');assert not failed['report']['all_passed']
    passed=run(client,course,REFERENCE,'exercise');assert passed['report']['all_passed']
    assert len(passed['report']['checks'])==3 and passed['report']['trace']
    assert client.get('/api/course').json()['demonstrated']==before['demonstrated']
    assert client.get('/api/session').json()['meta']['allowance']['reserved_cents']==0
    assert client.get('/api/meta/activity').json()['events']==[]


def test_activity_is_owner_bound_and_cleared_with_local_data(demo_client):
    client,_=demo_client
    assert client.get('/api/meta/activity').status_code==200
    assert client.delete('/api/my-data').status_code==200
    assert client.get('/api/meta/activity').status_code==401
    client.get('/api/session')
    assert client.get('/api/meta/activity').json()['events']==[]
