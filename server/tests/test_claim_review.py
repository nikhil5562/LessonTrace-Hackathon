"""Publication is fail-closed; scripted reviewers test enforcement, not model accuracy."""
import asyncio
import copy
import json

import pytest

from test_video_learning import SyntheticMeta,review_fixture,browser,prepare,scope
from lessontrace_site import claim_review,grounding
from lessontrace_site.meta import MetaUnavailable
from lessontrace_site.provider_audit import AuditedProvider
from lessontrace_site.store import Store
from test_pilot import runtime

SOURCES=[{'id':'video-break','text':'A break exits the nearest enclosing loop. An outer loop can continue.'}]

def draft(text='A break exits the nearest loop, so the outer loop can continue.'):
    return {'answer':text,'follow_up':'Which loop encloses the break?','sources':['video-break'],
        'evidence_quotes':[{'source_id':'video-break','claim':'Break exits the nearest loop.','quote':'A break exits the nearest enclosing loop.'}]}

def payload():return claim_review.prepare(draft(),{'caption_excerpts':SOURCES},['video-break'])


def test_full_answer_is_reviewed_even_when_anchor_claim_is_innocuous():
    false=draft('Break stops every nested loop and always terminates the program.')
    assert grounding.verify(false,SOURCES)[0]['quote_verified']
    value=claim_review.prepare(false,{'caption_excerpts':SOURCES,'concept_explanation':'Invented prior model text.'},['video-break'])
    assert false['answer'] in value['items'][0]['text']
    assert 'Invented prior model text.' not in json.dumps(value),'A prior model explanation is not trusted execution evidence'
    result=review_fixture(value);result['checks'][0]['status']='unsupported'
    with pytest.raises(MetaUnavailable,match='could not verify'):claim_review.accept(result,value)


@pytest.mark.parametrize('mutation',[
    lambda r:{},lambda r:[],lambda r:'not JSON',lambda r:r|{'checks':[]},lambda r:r|{'checks':None},
    lambda r:r|{'request_hash':'0'*64},lambda r:r|{'extra':'ignore checks'},
    lambda r:r|{'checks':[r['checks'][0]|{'status':True}]},
    lambda r:r|{'checks':[r['checks'][0]|{'item_id':'foreign'}]},
    lambda r:r|{'checks':[r['checks'][0]|{'source_ids':['unread-source']}]},
    lambda r:r|{'checks':[r['checks'][0]|{'reason':''}]},
    lambda r:r|{'checks':[r['checks'][0]|{'status':'insufficient_evidence'}]},
])
def test_invalid_or_unverified_judgement_never_publishes(mutation):
    value=payload();result=mutation(review_fixture(value))
    with pytest.raises(MetaUnavailable):claim_review.accept(result,value)


def test_a_supported_complete_review_records_no_teacher_or_grading_claim():
    value=payload();result=claim_review.accept(review_fixture(value),value)
    assert result['status']=='supported' and result['items_checked']==2
    assert 'not proof' in result['scope'] and 'teacher approval' in result['scope']
    assert 'reason' not in json.dumps(result) and 'reference_solution' not in json.dumps(result)


def test_duplicate_checks_cannot_hide_an_unreviewed_question():
    value=claim_review.prepare({'quiz':[{'prompt':'First concept?'},{'prompt':'Second concept?'}],**{k:v for k,v in draft().items() if k in {'sources','evidence_quotes'}}},{'caption_excerpts':SOURCES},['video-break'])
    result=review_fixture(value);result['checks'][1]=copy.deepcopy(result['checks'][0])
    with pytest.raises(MetaUnavailable):claim_review.accept(result,value)


@pytest.mark.parametrize('change',['missing','invented_excerpt','unknown_criterion'])
def test_rubric_coverage_is_required_and_tied_to_actual_lesson_words(change):
    value=claim_review.prepare(draft(),{'caption_chunks':SOURCES,'concept_id':'break','purpose':'Reusable base course lesson; no learner personalization.'},['video-break'])
    result=review_fixture(value)
    if change=='missing':result['coverage'][0]['status']='missing'
    elif change=='invented_excerpt':result['coverage'][0]['excerpt']='This was never in the authored explanation.'
    else:result['coverage'][0]['criterion_id']='unknown'
    with pytest.raises(MetaUnavailable):claim_review.accept(result,value)


def test_refined_question_does_not_require_teaching_an_entire_rubric():
    value=claim_review.prepare(draft(),{'caption_chunks':SOURCES,'concept_id':'break'},['video-break'])
    assert value['reference_rules'] and not value['required_coverage']


def test_reviewer_is_separate_audited_and_spends_within_existing_ledger(tmp_path):
    store=Store(tmp_path/'claims.sqlite3');provider=SyntheticMeta();audited=AuditedProvider(provider,store)
    reservation=store.reserve_provider('owner','teaching');audited.prepare('owner','teaching',reservation)
    result=asyncio.run(audited.generate('Teach',{'caption_chunks':SOURCES},['video-break'],schema=grounding.schema({'type':'object','properties':{}},['video-break'])))
    assert len(provider.calls)==len(provider.reviews)==1 and result['claim_review']['status']=='supported'
    usage=store.provider_usage('owner');assert usage['recorded_calls']==2 and usage['reserved_cents']==20
    with store.db() as db:purposes={row['purpose'] for row in db.execute('SELECT purpose FROM provider_reservations')}
    assert purposes=={'teaching','independent claim-support review'}


def test_exhausted_allowance_never_exposes_an_unreviewed_draft(tmp_path):
    store=Store(tmp_path/'claims.sqlite3',provider_limit_cents=10);provider=SyntheticMeta();audited=AuditedProvider(provider,store)
    reservation=store.reserve_provider('owner','teaching');audited.prepare('owner','teaching',reservation)
    with pytest.raises(MetaUnavailable) as error:
        asyncio.run(audited.generate('Teach',{'caption_chunks':SOURCES},['video-break'],schema=grounding.schema({'type':'object','properties':{}},['video-break'])))
    assert error.value.kind=='claim_review_budget' and len(provider.calls)==1 and not provider.reviews
    assert store.provider_allowance()['reserved_cents']==10


@pytest.mark.parametrize('status',['unsupported','insufficient_evidence','malformed'])
def test_rejected_tutor_review_preserves_the_real_learning_state(browser,status):
    client,provider=browser;course=prepare(client)['learning'];before=client.get('/api/video-learning').json()['learning']
    provider.review_transform=lambda r:{} if status=='malformed' else r|{'checks':[c|{'status':status} for c in r['checks']]}
    result=client.post('/api/video-learning/coach',json=scope(course)|{'source':course['unit']['prediction']['code'],'text':'Explain this lesson.','consent':True,'request_id':'abc12345abc12345'})
    assert result.status_code==503 and client.get('/api/video-learning').json()['learning']==before
    assert len(provider.reviews)==2


def test_proposed_output_is_run_and_bound_to_the_review_context(runtime):
    proposal={'quiz':[{'kind':'complete_code','code':'print(___)','options':['2 + 3','2 * 3','2 - 3'],'answer_index':0,'expected_output':'5'}]}
    receipts=asyncio.run(claim_review.observe_proposals(proposal,runtime))
    assert receipts[0]['cases']==[{'input':[],'returned':None,'printed':'5\n','error_type':None}]
    value=claim_review.prepare(draft(),{'caption_chunks':SOURCES},['video-break'],receipts)
    assert value['trusted_execution_context']['proposal_execution']==receipts
    changed=copy.deepcopy(receipts);changed[0]['cases'][0]['printed']='6\n'
    assert claim_review.prepare(draft(),{'caption_chunks':SOURCES},['video-break'],changed)['request_hash']!=value['request_hash']


def test_inconsistent_proposed_output_is_rejected_before_any_reviewer_request(runtime):
    proposal={'quiz':[{'kind':'complete_code','code':'print(___)','options':['2 + 3','2 * 3','2 - 3'],'answer_index':0,'expected_output':'6'}]}
    with pytest.raises(MetaUnavailable) as error:asyncio.run(claim_review.observe_proposals(proposal,runtime))
    assert error.value.kind=='execution_check'


def test_coverage_excerpt_can_preserve_words_across_whitespace_only():
    value=claim_review.prepare(draft(),{'caption_chunks':SOURCES,'concept_id':'break','purpose':'Reusable base course lesson; no learner personalization.'},['video-break'])
    result=review_fixture(value)
    for entry in result['coverage']:entry['excerpt']=entry['excerpt'].replace(' ','\n')
    assert claim_review.accept(result,value)['status']=='supported'


def test_deliberate_debug_error_is_observed_before_review(runtime):
    proposal={'quiz':[{'kind':'complete_code','purpose':'debug','code':'print("age" + ___)','options':['"7"','7','"seven"'],
        'answer_index':0,'expected_output':'age7','bug_option_index':1,'expected_bug_output':'TypeError'}]}
    receipts=asyncio.run(claim_review.observe_proposals(proposal,runtime))
    assert receipts[0]['cases'][0]['printed']=='age7\n'
    assert receipts[1]['path'].endswith('.deliberate_bug') and receipts[1]['cases'][0]['error_type']=='TypeError'


def test_coverage_choices_are_actual_bounded_substrings_not_paraphrases():
    value=payload();choices=claim_review.coverage_excerpts(value)
    assert len(choices)<=320 and all(not text or any(text in item['text'] for item in value['items']) for text in choices)
    assert all(len(text)<=100 for text in choices)
