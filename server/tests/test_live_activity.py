"""Call status must separate test transports, owners and model output from metadata."""
import asyncio
import json
import httpx
from lessontrace_site.meta import MetaProvider
from lessontrace_site.provider_audit import AuditedProvider
from lessontrace_site.store import Store


def test_activity_does_not_call_a_mock_live_or_expose_prompts(tmp_path):
    secret='fixture-only-do-not-display'
    def reply(request):
        return httpx.Response(200,json={'id':'fixture-response-id','model':'muse-spark-1.3','choices':[{'finish_reason':'stop','message':{'content':json.dumps({'answer':'private model text','sources':['original']})}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
    provider=MetaProvider(enabled=True,key=secret,transport=httpx.MockTransport(reply))
    store=Store(tmp_path/'usage.sqlite3');audited=AuditedProvider(provider,store)
    reservation=store.reserve_provider('one','original sample hint');audited.prepare('one','original sample hint',reservation)
    result=asyncio.run(audited.generate('private prompt',{'private':'code'},['original'],call_context={'session_id':'a'*32}))
    event=audited.activity_for('one')[0]
    assert event['mode']=='controlled-test' and event['status']=='response_received'
    assert event['request_id']=='fixture-response-id' and event['reported_tokens']['total_tokens']==15
    assert not audited.activity_for('two')
    assert all(x not in json.dumps(event) for x in (secret,'private prompt','private model text','private code'))
    audited.clear_activity('one');assert not audited.activity_for('one')


def test_live_flag_only_for_real_transport_and_safe_failures(tmp_path):
    class FailedMeta(MetaProvider):
        async def generate(self,*args,**kwargs):
            raise ValueError('sensitive failure details')
    store=Store(tmp_path/'usage.sqlite3');audited=AuditedProvider(FailedMeta(enabled=True,key='fixture'),store)
    audited.prepare('one','original sample',store.reserve_provider('one','original sample'))
    try:asyncio.run(audited.generate('private',{},[]))
    except ValueError:pass
    event=audited.activity_for('one')[0]
    assert event['status']=='failed' and event['failure']=='ValueError'
    assert event['mode']=='not-sent'
    assert 'sensitive' not in json.dumps(event)
