"""Bounded teaching decisions and evidence of supported/unaided attempts.

The model chooses teaching actions. Only the application can change activities
or award a checked result. No model statement is accepted as a mastery score.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pydantic import Field,ValidationError as SpecError

from .video_curriculum import Exercise,digest,source_schema,validate_exercise
from .meta import MetaUnavailable
from . import grounding

DAY=24*60*60
MAX_VARIANTS=8


class VariantExercise(Exercise):
    opening_question: str=Field(min_length=8,max_length=300)


def activity_state(kind='practice',supported=False):
    return {'kind':kind,'supported':supported,'attempts':0,'failures':0,'passed':False,
            'independent_run_id':None,'last_run_id':None,'expectation_requested':False,'learner_expectation':'','help_level':0}


def upgrade(progress,units):
    """Preserve existing drafts/results; old completion is not independent evidence."""
    if not progress.get('adaptive_version'):
        progress['adaptive_version']=1
        if progress.get('complete'):progress['legacy_completion']=True;progress['complete']=False
    progress.setdefault('transitions',[])
    for unit in units:unit_state(progress,unit['id'])
    return progress


def unit_state(progress,identifier):
    up=progress['units'].setdefault(identifier,{'phase':'prediction','predictions':[],'prediction_ok':False,'practice_passed':False,'hint_count':0,'viewed_execution':False,'last_run_id':None})
    up.setdefault('active_activity','practice');up.setdefault('variants',{});up.setdefault('activities',{})
    if 'practice' not in up['activities']:
        base=activity_state(supported=bool(up['hint_count']));base['passed']=up['practice_passed'];base['last_run_id']=up['last_run_id'];up['activities']['practice']=base
    up.setdefault('independent_passed',False);up.setdefault('review_due_at',None);up.setdefault('attempt_history',[]);up.setdefault('decisions',[])
    up.setdefault('quiz_answers',{});up.setdefault('quiz_skipped',False)
    for state in up['activities'].values():state.setdefault('help_level',0)
    return up


def active(up):return up['activities'][up['active_activity']]


def exercise_for(unit,up):
    return unit['exercise'] if up['active_activity']=='practice' else up['variants'][up['active_activity']]['exercise']


def next_step(progress,up,*,quiz_ready=None):
    if up['phase']=='prediction':return ('practice','Go to coding →') if (up['prediction_ok'] if quiz_ready is None else quiz_ready) else (None,'')
    state=active(up)
    if state['kind']=='review':
        if state['independent_run_id']:return 'resume','Return to my lesson →'
        return ('fresh_check','Try another check without hints →') if state['passed'] else (None,'')
    if state['kind']=='simpler':return ('return_practice','Return to the main exercise →') if state['passed'] else (None,'')
    if up['independent_passed']:return 'next','Next concept →'
    return ('fresh_check','Try a fresh check →') if state['passed'] and up['practice_passed'] else (None,'')


def observe_run(up,identifier,report,activity_id):
    state=up['activities'][activity_id]
    state['attempts']+=1;state['last_run_id']=identifier;state['passed']=report['all_passed']
    if not report['all_passed']:state['failures']+=1
    independent=state['kind'] in {'fresh','review'} and not state['supported'] and report['all_passed']
    report['activity_id']=activity_id;report['activity_kind']=state['kind'];report['supported']=state['supported'];report['independent_check']=independent
    if independent:
        state['independent_run_id']=identifier;up['independent_passed']=True;up['review_due_at']=time.time()+DAY
    if activity_id=='practice':up['practice_passed']=report['all_passed']
    errors=sorted({c['error']['type'] for c in report['checks'] if c.get('error')})
    up['attempt_history']=(up['attempt_history']+[{'run_id':identifier,'activity_id':activity_id,'kind':state['kind'],'passed':report['all_passed'],'supported':state['supported'],'independent':independent,'errors':errors,'at':time.time(),'origin':report['origin']}])[-40:]
    if up['active_activity']==activity_id:up['last_run_id']=identifier


def eligible_actions(up,report,text,intent):
    options=['hint','review_source','ask_expectation']
    state=active(up)
    if report and report.get('trace'):options.append('inspect_trace')
    expectation=bool(state['learner_expectation']) or state['expectation_requested'] and intent=='reply' or bool(re.search(r'\b(expect|expected|thought|wanted)\b',text,re.I))
    if state['expectation_requested'] or expectation:options.remove('ask_expectation')
    if state.get('help_level',0)>=2 and report and report.get('trace'):options.remove('hint')
    failed=bool(report and report.get('checks') and not report.get('all_passed'))
    if failed and not expectation and intent!='explain':
        # An exception alone cannot establish what the learner misunderstood.
        return ['ask_expectation','review_source'] if not state['expectation_requested'] else ['review_source']+(['inspect_trace'] if report.get('trace') else [])
    if state['failures']>=2 and expectation and not state['passed'] and len(up['variants'])<MAX_VARIANTS:
        options.append('simpler_practice')
    if state['passed'] and up['practice_passed'] and not state['independent_run_id'] and len(up['variants'])<MAX_VARIANTS:
        options.append('fresh_check')
    return options


def reject_repeated_hint(messages,activity_id,answer,learner_text):
    if re.search(r'\b(?:repeat|again please|same hint)\b',learner_text,re.I):return
    def normalized(text):return ' '.join(re.findall(r'\w+',text.casefold()))
    current=normalized(answer['answer'])
    follow_up=normalized(answer.get('follow_up',''))
    for message in messages[-8:]:
        if message['role']!='assistant' or message.get('activity_id')!=activity_id:continue
        if answer['action']=='hint' and len(current)>=25 and normalized(message['text'])==current:
            raise ValueError('Meta repeated an earlier hint. Your work was kept. Ask to inspect a trace step or source passage instead.')
        if len(follow_up)>=20 and normalized(message.get('follow_up',''))==follow_up:
            raise ValueError('Meta repeated an earlier follow-up question. Your work was kept. Ask to inspect the observed step or explain the source instead.')


def decision_schema(actions,source_ids):
    return grounding.schema({'type':'object','additionalProperties':False,'required':['answer','follow_up','sources','action','reason','source_id','trace_step'],
        'properties':{'answer':{'type':'string','minLength':1,'maxLength':2400},'follow_up':{'type':'string','minLength':1,'maxLength':400},
        'sources':{'type':'array','minItems':1,'maxItems':6,'items':{'type':'string','enum':source_ids}},
        'action':{'type':'string','enum':actions},'reason':{'type':'string','minLength':1,'maxLength':300},
        'source_id':{'type':'string','enum':source_ids},'trace_step':{'type':'integer','minimum':0,'maximum':350}}},source_ids)


COACH_INSTRUCTION='''You are LessonTrace's bounded adaptive tutor for this specific lesson. Choose exactly one available teaching action using the learner's explanation and actual execution evidence. The available actions are executable choices, not labels: review_source shows a retrieved source passage, inspect_trace selects an actual trace step, simpler_practice creates an easier exercise, fresh_check creates a new task to attempt without hints, hint gives a small hint, ask_expectation asks the learner what they expected.
An exception alone is not a diagnosis of a misconception. If the learner's expectation is unclear, ask what result they expected and why. For ask_expectation, put that one question in follow_up only; answer should briefly describe the observed situation without asking additional questions. Respond to replies to your previous question before introducing another. Use only supplied source excerpts, current code and actual checked results; explicitly distinguish untested code. Never claim mastery or promise improved learning. When research_topic is an available action, it starts one previously authorised, separate Loops research follow-up. Choose it only when another source-grounded explanation would help the stated need. Do not invent research findings or interrupt the current task. Confirmed learner_preferences guide explanation length and first-hint style, never correctness, objectives or evidence of learning.
Choose simpler_practice after repeated failures when the learner needs a smaller step within this concept. Choose fresh_check when supported practice has passed and the learner is ready to apply the concept to a new task. When choosing either generated-exercise action, do not invent a task contract in answer: another checked generation supplies the actual task. Do not choose another action just to avoid generating the requested smaller or fresh exercise when it is available. You cannot advance the lesson or change an objective.
On first help, describe the conceptual action without giving a finished expression, complete replacement statement or method-call syntax. Later you may name a method but leave arguments and the statement for the learner. For ask_expectation, avoid revealing the fix before hearing their thinking. For a fresh check do not reveal a solution or expected answer. Keep answer under 140 words. Use readable Markdown and Python None/True/False terms. In follow_up ask one new, short, unanswered reasoning question; its answer must not already appear in answer. Cite only supplied source IDs. reason must be one brief observation explaining the teaching choice, not hidden reasoning. source_id must identify a retrieved passage. trace_step is a zero-based index into the supplied trace summary (use 0 if irrelevant).'''


COACH_INSTRUCTION+='\nUse help_focus and help_level to make progress from earlier assistance. Do not repeat a previously answered expectation question or the same hint. A learner may explicitly request repetition. A fresh task still receives no unsolicited solution.'


async def make_variant(meta,execution,semaphore,reserve,who,unit,up,chunks,kind,preferences=None,session_id=None,course_topic_id=None):
    if len(up['variants'])>=MAX_VARIANTS:raise ValueError('This concept has reached the pilot limit for new exercises. Existing work is still saved.')
    source_ids=[c['id'] for c in chunks]
    prior=[unit['exercise']]+[v['exercise'] for v in up['variants'].values()]
    evidence={'concept':unit['title'],'concept_explanation':unit['explanation'],'original_contract':unit['exercise']['instructions'],
        'kind':kind,'learner_preferences':preferences or {},'caption_excerpts':chunks,'allowed_passage_ids':source_ids,'recent_attempts':up['attempt_history'][-4:],
        'avoid_repeating':[{'instructions':e['instructions'],'entry':e['entry'],'cases':e['cases']} for e in prior][-4:]}
    instruction='''Create ONE original Python function exercise for this video concept using the requested Exercise JSON schema. Confirmed learner_preferences guide presentation only; preserve the skill objective and checked correctness. Use only the supplied caption concepts. For kind simpler, reduce the number of reasoning steps and practise one prerequisite within the same objective. For kind fresh or review, require the same skill in a different task context or with a changed requirement; do not just rename a function or repeat old test inputs. Supply an unfinished starter, an independently correct reference_solution and three or four distinct argument/expected-return cases, including a boundary. State whether input changes are allowed. The learner must write their own solution; never reveal reference code in title, instructions or starter. Use only ordinary positional functions, scalar literals, lists/dictionaries with string keys, subscripts, assignments, comparisons/arithmetic, if, for/while, return, len/range, append, copy, get/keys/values/items/pop/popitem, and f-strings. No imports, annotations, classes, comprehensions, slices, private names, input(), exceptions/try, tuples as returned results or unsupported builtins. Keep under 60 lines and 350 trace events. Cite only the supplied source IDs. Python will check the reference solution and starter before this is shown.'''
    if course_topic_id:
        from .course_policy import instruction as policy_instruction
        evidence['concept_id']=course_topic_id
        instruction+='\n'+policy_instruction(course_topic_id)
        if unit['exercise'].get('kind')=='program':
            instruction+=' Override the earlier function wording: produce kind program with ordinary top-level learner code, no def/return. parameters lists the input variable names supplied separately for each case; entry is the distinct result variable to assign. Cases arguments match parameters in order. Include input meaning and sample values in the task, never a hidden wrapper. Do not reset those inputs inside the program.'
    previous=None;last_error=None
    for attempt in range(2):
        request=dict(evidence)
        if last_error:request['repair_request']=last_error;request['previous_exercise']=previous
        if len(json.dumps(request))>24000:raise ValueError('This exercise context is too large. Existing work was kept.')
        reserve(who,True,'adaptive '+kind+' exercise'+(' repair' if attempt else ''))
        try:
            result=await meta.generate(instruction+' Use only the exact allowed_passage_ids in sources and citations, never catalog IDs or other passages mentioned in earlier explanations. Include one short opening_question about the learner’s approach to THIS new task, without disclosing an expected result or solution. State every parameter’s meaning and iteration bounds in ordinary learner language; do not mention schema field names in the instructions.',request,source_ids,schema=source_schema(VariantExercise,source_ids),max_completion_tokens=2600,call_context={'session_id':session_id})
            anchors=grounding.verify(result,chunks)
            previous={k:v for k,v in result.items() if k in Exercise.model_fields}
            async with semaphore:exercise=await validate_exercise(result,execution,source_ids)
            if course_topic_id:
                from .course_policy import check_exercise,inferred,require_target
                check_exercise(exercise,course_topic_id);require_target(exercise['reference_solution'],course_topic_id)
                exercise['needs']=sorted(inferred(exercise['reference_solution'])-{course_topic_id});exercise['targets']=[course_topic_id]
            exercise['evidence_quotes']=anchors
            if any(exercise['instructions'].strip()==e['instructions'].strip() or (digest(exercise['reference_solution'])==digest(e['reference_solution']) and exercise['cases']==e['cases']) for e in prior):
                raise ValueError('This repeats an existing task. Change the task context or requirement and its inputs.')
            if kind in {'fresh','review'} and any(json.dumps(exercise['cases'],sort_keys=True)==json.dumps(e['cases'],sort_keys=True) for e in prior):
                raise ValueError('Fresh checks need new inputs, not repeated checks from earlier practice.')
            question=VariantExercise.model_validate({k:result[k] for k in VariantExercise.model_fields if k in result}).opening_question
            return {'id':uuid.uuid4().hex,'kind':kind,'exercise':exercise,'opening_question':question,'model':result['model'],'created':time.time()}
        except MetaUnavailable as error:
            if error.kind=='execution_check':
                last_error=str(error)[:600]
                continue
            if (getattr(meta,'last_failure',None) or {}).get('kind')!='schema':raise
            last_error='Return the complete requested exercise schema. Use only the exact allowed_passage_ids for all sources and inline citations, never catalog IDs or passages absent from this request.'
        except (ValueError,TypeError,KeyError) as error:
            last_error='Meta returned an incomplete exercise schema.' if isinstance(error,SpecError) else str(error)[:600]
    raise ValueError('The generated exercise did not pass Python validation. Existing work was kept. '+(last_error or ''))


def activate(up,variant):
    identifier=variant['id'];up['variants'][identifier]=variant;up['activities'][identifier]=activity_state(variant['kind'])
    up['active_activity']=identifier;up['phase']='exercise';up['last_run_id']=None


def public_activity(up):
    state=active(up)
    return {k:up[k] for k in ('phase','prediction_ok','practice_passed','hint_count','viewed_execution','last_run_id','independent_passed','review_due_at')}|{
        'active_activity':up['active_activity'],'activity_kind':state['kind'],'activity_passed':state['passed'],
        'supported':state['supported'],'attempt_count':state['attempts'],'expectation_requested':state['expectation_requested']}
