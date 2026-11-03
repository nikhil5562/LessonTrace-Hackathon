"""Evidence provenance, failure behaviour and owned usage; no live API calls."""
import asyncio
import json

import httpx
import pytest

from test_video_learning import browser,prepare,scope
from lessontrace_site import adaptive,grounding
from lessontrace_site.meta import MetaProvider,MetaUnavailable
from lessontrace_site.provider_audit import AuditedProvider
from lessontrace_site.store import Store


PASSAGES=[{'id':'video-test-1','text':'A break exits the nearest enclosing loop. The outer loop can continue.'}]
def answer():return {'sources':['video-test-1'],'evidence_quotes':[{'source_id':'video-test-1','claim':'A break leaves the nearest loop.','quote':'A break exits the nearest enclosing loop.'}]}


def test_exact_source_anchor_and_selected_source_coverage():
    checked=grounding.verify(answer(),PASSAGES)
    assert checked[0]['quote_verified']
    # Provenance is deliberately not presented as an entailment classifier.
    unrelated=answer();unrelated['evidence_quotes'][0]['claim']='This proves that all loops stop.'
    assert grounding.verify(unrelated,PASSAGES)[0]['quote_verified']
    missing=answer()|{'source_id':'video-test-2'}
    with pytest.raises(ValueError,match='Every cited'):grounding.verify(missing,PASSAGES)


@pytest.mark.parametrize('quote',['Break exits both loops.','A break  exits the nearest enclosing loop.','A break exits the nearest enclosing loop!'])
def test_valid_id_with_fabricated_or_changed_quote_rejected(quote):
    bad=answer();bad['evidence_quotes'][0]['quote']=quote
    with pytest.raises(ValueError,match='word for word'):grounding.verify(bad,PASSAGES)


def test_missing_unknown_or_long_anchors_rejected():
    for change in [{'evidence_quotes':[]},{'sources':['video-unread']},{'evidence_quotes':[{'source_id':'video-unread','claim':'Nearest loop rule.','quote':'A break exits the nearest enclosing loop.'}]}]:
        with pytest.raises(ValueError):grounding.verify(answer()|change,PASSAGES)
    long=' '.join(['word']*26);bad=answer();bad['evidence_quotes'][0]['quote']=long
    with pytest.raises(ValueError,match='25 words'):grounding.verify(bad,[{'id':'video-test-1','text':long}])


def test_bad_tutor_quote_keeps_work_and_consumed_reservation(browser):
    client,provider=browser;course=prepare(client)['learning'];before=client.get('/api/video-learning').json()
    generate=provider.generate
    async def altered(*args,**kwargs):
        result=await generate(*args,**kwargs);result['evidence_quotes'][0]['quote']='This sentence was never supplied.';return result
    provider.generate=altered
    response=client.post('/api/video-learning/coach',json=scope(course)|{'source':course['unit']['prediction']['code'],'text':'A hint please','consent':True,'request_id':'0123456789abcdef'})
    assert response.status_code==503 and 'word for word' in response.text
    assert client.get('/api/video-learning').json()['learning']==before['learning']
    usage=client.get('/api/coach',params={'lesson_id':course['lesson_id']}).json()['usage']
    assert usage['recorded_calls']==3 and usage['reserved_cents']==30 and usage['billed_cost_usd'] is None


def test_help_escalates_and_does_not_repeat_expectation():
    up={'activities':{'practice':adaptive.activity_state()},'active_activity':'practice','variants':{},'practice_passed':False}
    state=adaptive.active(up);state['failures']=2;report={'trace':[{'line':2}],'checks':[{}],'all_passed':False}
    assert adaptive.eligible_actions(up,report,'Help me.','hint')==['ask_expectation','review_source']
    state['expectation_requested']=True
    assert 'ask_expectation' not in adaptive.eligible_actions(up,report,'Still stuck.','hint')
    state['learner_expectation']='I expected both loops to stop.';state['help_level']=2
    options=adaptive.eligible_actions(up,report,'Another hint.','hint')
    assert 'hint' not in options and 'inspect_trace' in options and 'simpler_practice' in options
    assert adaptive.activity_state('fresh')['help_level']==0
    messages=[{'role':'assistant','activity_id':'practice','text':'Compare the key you requested with the actual dictionary keys.'}]
    reply={'action':'hint','answer':messages[0]['text']}
    with pytest.raises(ValueError,match='repeated'):adaptive.reject_repeated_hint(messages,'practice',reply,'I am stuck')
    adaptive.reject_repeated_hint(messages,'practice',reply,'Repeat the same hint please')
    adaptive.reject_repeated_hint(messages,'fresh',reply,'I am stuck')
    messages[0]['follow_up']='What result did you expect from this code?'
    with pytest.raises(ValueError,match='follow-up'):
        adaptive.reject_repeated_hint(messages,'practice',{'action':'review_source','answer':'Read this different explanation.','follow_up':messages[0]['follow_up']},'I already explained that.')


def test_audit_concurrency_ownership_failure_and_deletion(tmp_path):
    store=Store(tmp_path/'usage.sqlite3')
    class Provider:
        enabled=True
        async def generate(self,name,**kwargs):
            assert 'call_context' not in kwargs
            await asyncio.sleep(.002)
            if name=='fail':raise MetaUnavailable('Temporary failure','timeout')
            return {'model':'fixture','usage':{'prompt_tokens':12,'completion_tokens':8,'total_tokens':20},'answer':'private content'}
    audited=AuditedProvider(Provider(),store)
    async def call(owner,session,name):
        reservation=store.reserve_provider(owner,'controlled test');audited.prepare(owner,'controlled test',reservation)
        try:await audited.generate(name,call_context={'session_id':session})
        except MetaUnavailable:pass
    async def check():
        with pytest.raises(MetaUnavailable,match='reservation'):await audited.generate('unreserved')
        await asyncio.gather(call('owner-a','a'*32,'ok'),call('owner-b','b'*32,'fail'))
    asyncio.run(check())
    a=store.provider_usage('owner-a','a'*32);b=store.provider_usage('owner-b','b'*32)
    assert a['recorded_calls']==1 and a['reported_total_tokens']==20 and a['calls_with_usage']==1
    assert b['failed_calls']==1 and b['calls_with_usage']==0 and b['reserved_cents']==10
    assert not store.provider_usage('owner-a','b'*32)['recorded_calls']
    with store.db() as db:
        rows=[dict(row) for row in db.execute('SELECT * FROM provider_calls')]
    assert next(row for row in rows if row['owner']=='owner-b')['failure']=='timeout' and 'private content' not in json.dumps(rows)
    before=store.provider_allowance();store.delete_owner('owner-a')
    assert not store.provider_usage('owner-a')['recorded_calls'] and store.provider_allowance()==before
    assert Store(store.path).provider_allowance()==before


@pytest.mark.parametrize(('status','kind'),[(402,'billing'),(429,'rate_limit'),(503,'http_503'),('timeout','timeout'),('network','network')])
def test_provider_failure_is_classified_without_hidden_retries(status,kind):
    calls=[]
    def handler(request):
        calls.append(request)
        if status=='timeout':raise httpx.ReadTimeout('Fixture timeout')
        if status=='network':raise httpx.ConnectError('Fixture network failure')
        return httpx.Response(status,text='PRIVATE PROVIDER ERROR')
    provider=MetaProvider(enabled=True,key='fixture-only',transport=httpx.MockTransport(handler))
    with pytest.raises(MetaUnavailable) as error:asyncio.run(provider.generate('Test',{},['video-test-1']))
    assert error.value.kind==kind and len(calls)==1 and 'PRIVATE PROVIDER ERROR' not in str(error.value)
