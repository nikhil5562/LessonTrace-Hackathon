"""A saved teaching correction must not reset attempts or alter coding tasks."""
import asyncio
import copy
import hashlib

import pytest

from test_hub import hub_browser,ready
from test_video_learning import scope
from test_teaching_quality import NESTED,question
from lessontrace_site.teaching_revision import checked_revision,publish_revision
from lessontrace_site.video_learning import progress_key


def fixture(hub_browser):
    client,_,_,app=hub_browser;ready(client)
    who=hashlib.sha256(client.cookies.get('lessontrace_browser').encode()).hexdigest();store=app.state.store
    record=store.progress(who)['hub_session'];unit=record['curriculum']['units'][0];sources=unit['sources']
    q=question();q['sources']=sources
    answer='## The complete example\n```python\n'+NESTED+'\n```\n\nThe outer loop reads 1 and then 2 from its shown list. Each time, the inner loop starts by reading 10 from its own list. The first break stops that inner loop. Execution resumes at row done inside the outer body, before the next outer iteration. ['+sources[0]+']'
    patch={'answer':answer,'explanation':'The outer and inner loops read values from their shown lists. Break exits the nearest loop, then the remaining outer-body statements run.','quiz':[q],'model':'synthetic-revision-model'}
    return client,app,who,store,record,unit,patch


def test_checked_correction_preserves_contract_progress_identity_and_library(hub_browser):
    client,app,who,store,record,unit,patch=fixture(hub_browser)
    course=client.get('/api/video-learning?context=hub').json()['learning'];q=course['unit']['quiz'][0]
    result=client.post('/api/video-learning/quiz',json=scope(course)|{'question_id':q['id'],'question_hash':q['question_hash'],'option':0});assert result.status_code==200
    before=store.progress(who)[progress_key(record['lesson_id'])]
    updated=asyncio.run(checked_revision(record,unit['id'],patch,app.state.runner))
    assert updated['curriculum']['units'][0]['exercise']==unit['exercise']
    assert updated['curriculum']['units'][0]['prediction']==unit['prediction']
    publish_revision(store,who,record,updated)
    assert store.progress(who)[progress_key(record['lesson_id'])]==before
    assert store.saved_lesson(who,record['lesson_id'])==store.progress(who)['hub_session']==updated
    after=client.get('/api/video-learning?context=hub').json()['learning'];assert after['lesson_id']==record['lesson_id']
    assert not after['progress']['quiz']['items'][0]['attempted'],'An answer for the old question must not count for its corrected code.'
    assert 'reference_solution' not in client.get('/api/video-learning?context=hub').text


def test_stale_revision_is_rejected_before_any_copy_changes(hub_browser):
    _,app,who,store,record,unit,patch=fixture(hub_browser)
    updated=asyncio.run(checked_revision(record,unit['id'],patch,app.state.runner))
    changed=copy.deepcopy(record);changed['title']='Changed while correcting';store.set_progress(who,'hub_session',changed)
    with pytest.raises(ValueError,match='changed while'):publish_revision(store,who,record,updated)
    assert store.progress(who)['hub_session']==changed and store.saved_lesson(who,record['lesson_id'])==record


def test_revision_cannot_publish_to_another_owner(hub_browser):
    _,app,_,store,record,unit,patch=fixture(hub_browser)
    updated=asyncio.run(checked_revision(record,unit['id'],patch,app.state.runner))
    with pytest.raises(ValueError,match='not found'):publish_revision(store,'other-browser',record,updated)
