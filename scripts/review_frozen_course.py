"""Audit existing immutable lessons with actual execution and independent rubrics.

No base file is changed. No API request occurs without --live.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'server'))
from lessontrace_site import claim_review,course_rubrics,course_errata
from lessontrace_site.course_catalog import VERSION,ORDER,topic
from lessontrace_site.course_sources import loader
from lessontrace_site.meta import MetaProvider,MetaUnavailable
from lessontrace_site.provider_audit import AuditedProvider
from lessontrace_site.store import Store
from lessontrace_site.runner import WasiRunner


async def expand_sources(artifact,concept,reader):
    """Expand only the same identified passage when its original anchors still match."""
    results=await asyncio.gather(*(reader.read(item['id'],concept,topic(concept)['title']) for item in artifact['source_documents']))
    full={chunk['id']:chunk for source in results for chunk in source['chunks']};chunks=[];expanded=0
    for saved in artifact['caption_chunks']:
        candidate=full.get(saved['id']);anchors=[q['quote'] for q in artifact['curriculum']['evidence_quotes'] if q['source_id']==saved['id']]
        same=candidate and all(saved.get(key)==candidate.get(key) for key in ('source_id','heading','start')) and saved.get('source_offset',0)==candidate.get('source_offset',0)
        if same and anchors and all(anchor in candidate['text'] for anchor in anchors):
            chunks.append(candidate);expanded+=1
        else:chunks.append(saved)
    return chunks,{'expanded_passages':expanded,'total_passages':len(chunks),'source_hashes':{s['id']:s['content_hash'] for s in results},
        'rule':'Same passage identity, section/time/offset and all original short anchors must match before expanding. Unmatched passages stay as frozen anchors.'}


async def packs(execution,concepts,reader=None):
    batches=[]
    manifest=json.loads((ROOT/'course_content'/VERSION/'manifest.json').read_text(encoding='utf-8'))
    for concept in concepts:
        raw=(ROOT/'course_content'/VERSION/(concept+'.json')).read_bytes();entry=manifest['lessons'][concept]
        if manifest.get('version')!=VERSION or entry['file']!=concept+'.json' or hashlib.sha256(raw).hexdigest()!=entry['sha256']:
            raise ValueError('The audit source does not match the frozen course manifest: '+concept)
        artifact=course_errata.apply(json.loads(raw),raw)
        receipts=await claim_review.observe_proposals(artifact['curriculum'],execution)
        chunks,context=await expand_sources(artifact,concept,reader) if reader else (artifact['caption_chunks'],{'expanded_passages':0,'total_passages':len(artifact['caption_chunks'])})
        payload=claim_review.prepare(artifact['curriculum'],{'caption_chunks':chunks,'concept_id':concept,
            'purpose':'Reusable base course lesson; no learner personalization.'},[p['id'] for p in chunks],receipts)
        payload['source_context']=context;payload['request_hash']=hashlib.sha256(claim_review._json({k:v for k,v in payload.items() if k!='request_hash'}).encode()).hexdigest()
        batches.append({concept:payload})
    return batches


async def run(args):
    execution=WasiRunner(ROOT/'.local/course-audit');execution.cache=ROOT/'.local/wasi-cache'
    try:
        await execution.warmup();assert execution.ready,execution.error
        concepts=args.concept or ORDER;batches=await packs(execution,concepts,loader(ROOT/'.local/course-source-cache') if args.expanded_sources else None)
    finally:await execution.close()
    print(json.dumps({'lessons':len(concepts),'review_requests':len(batches),'batch_sizes':[len(b) for b in batches],'max_chars':max(len(json.dumps(b)) for b in batches),'proposal_execution':'Observed with actual bounded Python'}),flush=True)
    if not args.live:return
    assert len(batches)<=args.max_requests
    store=Store(ROOT/'.local/lessontrace.sqlite3',None,provider_limit_cents=args.test_limit_cents)
    assert store.provider_allowance()['remaining_requests']>=len(batches)
    provider=AuditedProvider(MetaProvider(enabled=True),store);who='course-review-'+uuid.uuid4().hex;session=uuid.uuid4().hex
    report={'course_version':VERSION,'review_version':claim_review.VERSION,'rubric_version':course_rubrics.VERSION,'rubric_hash':course_rubrics.digest(),
        'human_teacher_approved':False,'scope':'Separate automated source/claim and topic-coverage audit of immutable base content plus hash-bound wording errata; not a publication approval, human teacher approval or proof.',
        'review_prompt_sha256':hashlib.sha256(claim_review.INSTRUCTION.encode()).hexdigest(),'execution_evidence':True,'wording_errata_version':course_errata.VERSION,
        'expanded_source_mode':args.expanded_sources,
        'coverage_format':'backend-selected literal excerpts v1',
        'lessons':{},'requests':0,'reservation_before_cents':store.provider_allowance()['reserved_cents']}
    try:
        for batch in batches:
            schema={'type':'object','additionalProperties':False,'required':['lessons'],'properties':{'lessons':{'type':'object','additionalProperties':False,
                'required':list(batch),'properties':{name:claim_review.schema(p) for name,p in batch.items()}}}}
            reservation=store.reserve_provider(who,'frozen course claim and rubric audit');provider.prepare(who,'frozen course claim and rubric audit',reservation)
            report['requests']+=1
            response=None;provider_error=None
            try:
                response=await provider.generate(claim_review.INSTRUCTION+' This request contains independent lessons. Review each using only its own sources and reference rules. Return an object with lessons mapping each concept to its full individual judgement. Keep the JSON compact: reasons under 100 characters, at most one relevant source ID per check, and coverage excerpts 8–100 characters. Do not restate the lesson. For a supported check a short reason such as Supported by supplied evidence is sufficient.',
                    {'review_task':'batch-'+claim_review.VERSION,'lessons':batch},list({p['id'] for payload in batch.values() for p in payload['sources']}),schema=schema,max_completion_tokens=6500,call_context={'session_id':session})
            except MetaUnavailable as error:provider_error=error.kind
            for concept,payload in batch.items():
                raw=(ROOT/'course_content'/VERSION/(concept+'.json')).read_bytes();entry={'content_sha256':hashlib.sha256(raw).hexdigest(),'source_context':payload['source_context']}
                if provider_error:entry.update(status='unavailable',failure=provider_error)
                else:
                    judgement=response['lessons'][concept]
                    try:entry['review']=claim_review.accept(judgement|{'model':response['model']},payload);entry['status']='supported'
                    except MetaUnavailable as error:
                        entry.update(status='needs_review',failure=error.kind,problems=[c for c in judgement.get('checks',[]) if c.get('status')!='supported'],coverage_problems=judgement.get('coverage',[]))
                report['lessons'][concept]=entry;print(json.dumps({'concept':concept,'status':entry['status'],'failure':entry.get('failure')}),flush=True)
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    finally:
        report.update(reservation_after_cents=store.provider_allowance()['reserved_cents'],qa_identity='Removed; reservations retained');store.delete_owner(who)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    report['summary']={'total':len(report['lessons']),'supported':sum(x['status']=='supported' for x in report['lessons'].values()),'needs_review':sum(x['status']!='supported' for x in report['lessons'].values())}
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report['summary']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');parser.add_argument('--expanded-sources',action='store_true');parser.add_argument('--test-limit-cents',type=int,default=100);parser.add_argument('--max-requests',type=int,default=24);parser.add_argument('--concept',action='append',choices=ORDER);parser.add_argument('--output',type=Path,default=ROOT/'.local/frozen-course-claim-review.json');asyncio.run(run(parser.parse_args()))
