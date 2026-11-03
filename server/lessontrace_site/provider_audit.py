"""Content-free usage records linked to the existing conservative reservations."""
from __future__ import annotations

from contextvars import ContextVar
import re
import time

from .meta import MetaUnavailable


class AuditedProvider:
    def __init__(self,provider,store,execution=None):
        self.provider,self.store,self.execution=provider,store,execution
        self.pending=ContextVar('lessontrace_model_reservation',default=None)
        self.review_reserve=None
        self.activity={}

    def __getattr__(self,name):return getattr(self.provider,name)

    def prepare(self,owner,purpose,reservation):self.pending.set({'owner':owner,'purpose':purpose,'reservation_id':reservation})

    def activity_for(self,owner):return [dict(event) for event in self.activity.get(owner,[])][-20:]

    def clear_activity(self,owner):self.activity.pop(owner,None)

    async def generate(self,*args,call_context=None,**options):
        from . import claim_review
        context=self.pending.get()
        result=await self.invoke('generate',args,options,call_context)
        if 'evidence_quotes' not in (options.get('schema') or {}).get('properties',{}):return result
        try:
            claim_review.prepare(result,args[1],args[2])
            receipts=await claim_review.observe_proposals(result,self.execution)
            payload=claim_review.prepare(result,args[1],args[2],receipts)
        except (ValueError,TypeError,KeyError) as error:
            raise MetaUnavailable(str(error)[:500],'claim_review_context') from None
        purpose='independent claim-support review'
        if self.review_reserve:self.review_reserve(context['owner'],True,purpose)
        else:
            try:reservation=self.store.reserve_provider(context['owner'],purpose)
            except ValueError:raise MetaUnavailable('The explanation needs a separate review request, but the approved allowance is used. Your work was kept.','claim_review_budget') from None
            self.prepare(context['owner'],purpose,reservation)
        try:
            judgement=await self.invoke('generate',(claim_review.INSTRUCTION,payload,args[2]),
                {'schema':claim_review.schema(payload),'max_completion_tokens':min(6500,max(2600,1000+len(payload['items'])*200+len(payload['required_coverage'])*150))},call_context)
        except MetaUnavailable as error:
            if error.kind in {'schema','invalid_response','incomplete'}:raise MetaUnavailable('The independent explanation review was incomplete or invalid. Your current work was kept.','claim_review_invalid') from None
            raise
        result['claim_review']=claim_review.accept(judgement,payload)
        return result

    async def transcribe(self,*args,**options):return await self.invoke('transcribe',args,options,None)

    async def invoke(self,method,args,options,call_context):
        context=self.pending.get();self.pending.set(None)
        if not context:raise MetaUnavailable('A model request needs a recorded allowance reservation first.')
        session=(call_context or {}).get('session_id')
        if session is not None and not re.fullmatch(r'[a-f0-9]{32}',session):raise ValueError('Invalid model-usage session identity.')
        started=time.perf_counter();result=None;failure=None
        from .meta import MetaProvider
        instrumented=isinstance(self.provider,MetaProvider)
        event={'id':context['reservation_id'],'session_id':session,'purpose':context['purpose'][:120],
            'mode':'not-sent' if instrumented else 'controlled-test','endpoint':'https://api.meta.ai/v1/'+('asr/transcribe' if method=='transcribe' else 'chat/completions'),
            'model':'muse-voice-transcribe-1.0' if method=='transcribe' else 'muse-spark-1.3',
            'started_at':time.time(),'status':'preparing','request_id':None}
        events=self.activity.setdefault(context['owner'],[]);events.append(event);events[:]=events[-40:]
        def sending(model,endpoint,live):event.update(model=model,endpoint=endpoint,mode='live' if live else 'controlled-test',status='sending')
        observer_token=self.provider.request_observer.set(sending) if instrumented else None
        try:
            result=await getattr(self.provider,method)(*args,**options)
            return result
        except BaseException as error:
            failure=getattr(error,'kind',None) or type(error).__name__
            raise
        finally:
            if observer_token is not None:self.provider.request_observer.reset(observer_token)
            self.store.record_provider_call(context,session,result,int((time.perf_counter()-started)*1000),failure)
            usage=(result or {}).get('usage') or {}
            event.update(status='failed' if failure else 'response_received',finished_at=time.time(),latency_ms=int((time.perf_counter()-started)*1000),
                failure=str(failure)[:60] if failure else None,request_id=str((result or {}).get('request_id',''))[:160] or None,
                reported_tokens={key:value for key,value in usage.items() if key in {'prompt_tokens','completion_tokens','total_tokens'} and isinstance(value,int)} if isinstance(usage,dict) else {})
