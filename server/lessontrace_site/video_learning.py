"""Private current-video learning sessions: Meta teaching, Python execution evidence."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Literal

from fastapi import HTTPException,Request
from pydantic import BaseModel,Field,ValidationError as SpecError
from jsonschema import validate as validate_response,ValidationError
from . import video_lessons as video
from . import adaptive
from . import video_quiz
from . import grounding
from .retrieval import retrieve
from .teaching_quality import QUALITY_INSTRUCTION
from .guest import validate
from .meta import MetaUnavailable
from .video_curriculum import INSTRUCTION,Lesson,QuizBatch,case_passed,digest,source_schema,validate_lesson,validate_quiz,exercise_payload


class Scope(BaseModel):
    lesson_id: str=Field(pattern=r'^[a-f0-9]{32}$')
    unit_id: str=Field(max_length=36)


class PredictionInput(Scope):
    option: int=Field(ge=0,le=3)
    source_hash: str=Field(pattern=r'^[a-f0-9]{64}$')


class QuizInput(Scope):
    question_id: str=Field(max_length=40)
    question_hash: str=Field(pattern=r'^[a-f0-9]{64}$')
    option: int=Field(ge=0,le=3)


class QuizPrepareInput(Scope):
    consent: bool=False
    request_id: str=Field(pattern=r'^[a-f0-9-]{16,40}$')


class MoveInput(Scope):
    action: Literal['practice','next','fresh_check','return_practice','review','resume','skip_quiz','quiz']
    consent: bool=False
    request_id: str | None=Field(default=None,pattern=r'^[a-f0-9-]{16,40}$')
    review_unit_id: str | None=Field(default=None,max_length=36)


class RunInput(Scope):
    source: str=Field(min_length=1,max_length=8000)
    mode: Literal['prediction','exercise','explore']
    trace_case: int=Field(default=0,ge=0,le=3)
    origin: Literal['learner','qa_walkthrough']='learner'
    activity_id: str | None=Field(default=None,max_length=40)


class ChatInput(Scope):
    text: str=Field(min_length=1,max_length=1200)
    source: str=Field(max_length=8000)
    run_id: str | None=None
    step: int=Field(default=0,ge=0,le=350)
    consent: bool=False
    request_id: str=Field(pattern=r'^[a-f0-9-]{16,40}$')
    activity_id: str | None=Field(default=None,max_length=40)
    intent: Literal['reply','hint','explain','next']='reply'
    quiz_question_id: str | None=Field(default=None,max_length=40)


def progress_key(lesson_id):return 'video_progress_'+lesson_id


def blank_progress(record):
    first=record['curriculum']['units'][0]
    progress={'adaptive_version':1,'current_unit':0,'complete':False,'units':{},'transitions':[],'messages':[{'role':'assistant','text':first['opening_question'],'follow_up':'','sources':first['sources'],'unit_id':first['id'],'at':time.time(),'kind':'opening'}]}
    if record.get('course_flow')=='lesson-first':
        state=unit_progress(progress,first['id']);state['phase']='lesson';state['lesson_opened']=False
    return progress


def unit_progress(progress,identifier):
    return adaptive.unit_state(progress,identifier)


def public_state(record,progress):
    adaptive.upgrade(progress,record['curriculum']['units'])
    units=record['curriculum']['units'];unit=units[progress['current_unit']]
    state=unit_progress(progress,unit['id'])
    exercise=adaptive.exercise_for(unit,state)
    quiz=video_quiz.status(unit,state)
    next_action,next_label=adaptive.next_step(progress,state,quiz_ready=quiz['complete'] or quiz['skipped'])
    if record.get('course_flow')=='lesson-first':
        if state['phase']=='lesson':next_action,next_label='quiz','Start the topic check →'
        elif state['phase']=='exercise' and state['practice_passed'] and video_quiz.assessment_ready(unit,state):next_action,next_label='next','Next lesson →'
    if record.get('context')=='course' and next_action=='fresh_check' and state['active_activity']=='practice' and not video_quiz.assessment_ready(unit,state):next_action,next_label='quiz','Finish the topic check →'
    reviews=[{'unit_id':u['id'],'title':u['title'],'due_at':unit_progress(progress,u['id'])['review_due_at']} for u in units if unit_progress(progress,u['id'])['review_due_at']]
    return {'lesson_id':record['lesson_id'],'context':record.get('context','video'),'course_flow':record.get('course_flow'),'title':record['title'],'video_id':record['video_id'],
        'course_info':{k:record[k] for k in ('course_version','course_concept','course_unit','course_role','course_parent') if k in record},
        'frozen_fresh_available':record.get('context')=='course' and bool(unit.get('fresh_exercise')) and not any(v.get('frozen') for v in state['variants'].values()),
        'concepts':[{'id':u['id'],'title':u['title'],'done':progress['units'].get(u['id'],{}).get('independent_passed',False)} for u in units],
        'unit_index':progress['current_unit'],'unit':{'id':unit['id'],'title':unit['title'],'explanation':unit['explanation'],'sources':unit['sources'],
            'quiz':[video_quiz.public_question(q) for q in video_quiz.questions(unit)],
            'prediction':{k:v for k,v in unit['prediction'].items() if k in {'prompt','code','options','sources'}}|{'source_hash':digest(unit['prediction']['code'])},
            'exercise':{k:v for k,v in exercise.items() if k in {'kind','parameters','needs','targets','title','instructions','entry','starter','preserve_input','sources'}}|{'test_count':len(exercise['cases']),
                'input_example':dict(zip(exercise.get('parameters',[]),exercise['cases'][0]['arguments'])) if exercise.get('kind')=='program' else None,
                'call_example':{'entry':exercise['entry'],'arguments':exercise['cases'][0]['arguments']} if exercise.get('kind','function')=='function' else None}},
        'progress':adaptive.public_activity(state)|{'complete':progress['complete'],'next_action':next_action,'next_label':next_label,'reviewing':bool(progress.get('review_resume')),'quiz':quiz,'lesson_opened':state.get('lesson_opened',False)},
        'messages':[{k:v for k,v in message.items() if k in {'role','text','follow_up','sources','unit_id','at','kind','model','action_result','evidence_quotes','claim_review'}} for message in progress['messages'][-50:]],
        'reviews':reviews,'evidence':state['attempt_history'][-12:],
        'validation':'Reference code checked with CPython. A fresh-check pass means no tutor help was recorded for that task; it is not a mastery score.'}


def install_video_learning_routes(app,owner,store,execution,meta,reserve_cloud,tasks,semaphore,coach=None,course_service=None):
    generating=set();chatting=set();cache=store.path.parent/'video-captions'

    def current(who,scope=None,lesson_id=None,context='video'):
        data=store.progress(who);identifier=scope.lesson_id if scope else lesson_id
        record=next((data.get(key) for key in ('youtube_session','hub_session','course_session') if data.get(key,{}).get('lesson_id')==identifier),None) if identifier else data.get({'hub':'hub_session','course':'course_session'}.get(context,'youtube_session'))
        if not record or not record.get('curriculum'):raise HTTPException(409,'This lesson is no longer current. Reopen your video or deep dive before continuing.')
        if course_service and record.get('context')=='course':
            corrected=course_service.teaching_record(who,record)
            if corrected!=record:store.set_progress(who,'course_session',corrected)
            record=corrected
        progress=data.get(progress_key(record['lesson_id'])) or blank_progress(record)
        adaptive.upgrade(progress,record['curriculum']['units'])
        unit=record['curriculum']['units'][progress['current_unit']]
        if scope and unit['id']!=scope.unit_id:raise HTTPException(409,'This is not the active concept. Refresh the lesson.')
        unit_progress(progress,unit['id'])
        if course_service:course_service.access(who,record,unit)
        return record,progress,unit

    def save(who,record,progress):
        store.set_progress(who,progress_key(record['lesson_id']),progress)
        if coach:coach.observe(who,record,progress)
        if course_service:course_service.observe(who,record,progress)

    def check_activity(up,identifier):
        if (identifier or 'practice')!=up['active_activity']:raise HTTPException(409,'The exercise changed. Refresh before running or asking about this code.')

    def busy(who):
        if who in generating or who in chatting:raise HTTPException(409,'The tutor is finishing the previous action. Your draft is saved.')

    def passages(record,text,unit):
        return retrieve(record['caption_chunks'],text,unit['sources'])

    async def variant(who,unit,up,record,kind):
        if record.get('context')=='course' and kind=='fresh' and unit.get('fresh_exercise') and not any(v.get('frozen') for v in up['variants'].values()):
            return {'id':uuid.uuid4().hex,'kind':'fresh','exercise':unit['fresh_exercise'],'opening_question':'What approach will you try for this different task?','model':record.get('model'),'created':time.time(),'frozen':True}
        chunks=passages(record,unit['title']+' '+unit['exercise']['instructions'],unit)
        try:return await adaptive.make_variant(meta,execution,semaphore,reserve_cloud,who,unit,up,chunks,kind,coach.teaching_preferences(who) if coach else None,session_id=record['lesson_id'],course_topic_id=record.get('course_concept'))
        except (ValueError,MetaUnavailable) as error:raise HTTPException(503,str(error)) from None

    @app.post('/api/video-session/learning')
    async def generate(body: video.VideoInput,request: Request):
        who=owner(request,True)
        if not body.consent or not meta.enabled:raise HTTPException(409,'Allow Meta processing before preparing the video lesson.')
        if not execution.ready:raise HTTPException(503,'Python is still warming up. Try preparing the lesson again shortly.')
        if who in generating:raise HTTPException(409,'This browser is already preparing a video lesson.')
        generated_id=uuid.uuid4().hex
        generating.add(who)
        try:
            try:identifier=video.video_id(body.url)
            except ValueError as error:raise HTTPException(422,str(error)) from None
            if body.end_seconds is not None and body.end_seconds<=body.start_seconds:raise HTTPException(422,'The end time must be after the start time.')
            if body.caption_text.strip():
                if not body.caption_reviewed:raise HTTPException(409,'Review the pasted caption text first.')
                chunks=[{'id':f'video-{identifier}-manual','start':None,'end':None,'text':body.caption_text.strip()}]
                source='Learner-supplied captions; timing and completeness unverified';language='as supplied';automatic=None
            else:
                try:
                    captions=await asyncio.wait_for(asyncio.to_thread(video.fetch_captions,identifier,cache),35)
                    chunks=video.source_chunks(identifier,captions,body.start_seconds,body.end_seconds)
                except ValueError as error:raise HTTPException(422,str(error)) from None
                except Exception:raise HTTPException(503,'The public captions could not be retrieved. Try later or paste reviewed captions under More options. No model request was made.') from None
                source=captions['origin'];language=captions['language'];automatic=captions['is_generated']
            evidence={'caption_source':source,'caption_chunks':chunks,'coverage':'Captions only; no fresh audio or video frame analysis.',
                'learner_preferences':coach.teaching_preferences(who) if coach else {}}
            if len(json.dumps(evidence))>24000:raise HTTPException(422,'Choose a shorter video section before preparing this lesson.')
            source_ids=[c['id'] for c in chunks]
            evidence['allowed_passage_ids']=source_ids
            last_error=None;result=None
            for attempt in range(2):
                request_evidence=dict(evidence)
                if last_error:
                    request_evidence['repair_request']=last_error
                    prior=(result or {}).get('units',[])
                    if len(json.dumps(request_evidence|{'previous_units':prior}))<=24000:request_evidence['previous_units']=prior
                reserve_cloud(who,True,'Meta current-video curriculum'+(' repair' if attempt else ''))
                try:result=await meta.generate(INSTRUCTION,request_evidence,source_ids,schema=source_schema(Lesson,source_ids),max_completion_tokens=6500,call_context={'session_id':generated_id})
                except MetaUnavailable as error:
                    if error.kind=='execution_check':last_error=str(error);continue
                    raise HTTPException(503,str(error)) from None
                try:
                    async with semaphore:spec=await validate_lesson(result,execution,source_ids,chunks)
                    break
                except (ValueError,KeyError,TypeError) as error:
                    last_error='Meta returned an incomplete lesson schema.' if isinstance(error,SpecError) else str(error)[:600]
                    (store.path.parent/'video-generation-debug.json').write_text(json.dumps({'error':last_error,'generated':result},ensure_ascii=True,indent=2),encoding='utf-8')
            else:raise HTTPException(503,'Meta’s generated lesson did not pass the Python consistency checks. Existing notes were kept. Try again. '+(last_error or ''))
            record={k:v for k,v in result.items() if k in {'provider','model','request_id','usage','claim_review'}}|{
                'lesson_id':generated_id,'interactive':True,'title':spec['title'],'answer':spec['answer'],'sources':spec['sources'],'curriculum':spec,
                'video_id':identifier,'url':'https://www.youtube.com/watch?v='+identifier,'caption_source':source,'caption_chunks':chunks,'language':language,'auto_generated':automatic,
                'created':time.time(),'coverage':'Meta-generated from available captions. Audio and video frames were not analysed separately.',
                'practice_topic':None,'practice_basis':'Concepts, prediction code and exercises generated by Meta for this video. Reference code checked with Python.'}
            if coach:coach.remember(who,store.progress(who).get('youtube_session'))
            progress=blank_progress(record);save(who,record,progress);store.set_progress(who,'youtube_session',record)
            return {'session':video.public_session(record),'learning':public_state(record,progress),'allowance':store.provider_allowance()}
        finally:generating.discard(who)

    @app.get('/api/video-learning')
    async def state(request: Request,context: Literal['video','hub','course']='video'):
        who=owner(request)
        record=store.progress(who).get({'hub':'hub_session','course':'course_session'}.get(context,'youtube_session'))
        if not record or not record.get('curriculum'):return {'learning':None,'upgrade_available':bool(record)}
        record,progress,_=current(who,context=context)
        return {'learning':public_state(record,progress),'allowance':store.provider_allowance()}

    @app.post('/api/video-learning/predict')
    async def predict(body: PredictionInput,request: Request):
        who=owner(request,True);busy(who);record,progress,unit=current(who,body);question=unit['prediction'];up=unit_progress(progress,unit['id'])
        if record.get('context')=='course' and up['phase']!='prediction':raise HTTPException(409,'Reopen the topic check before answering. A stale prediction cannot change the independent task.')
        if body.source_hash!=digest(question['code']):raise HTTPException(409,'Restore the original prediction snippet before answering. Your edited version can still be run as exploration.')
        if body.option>=len(question['options']):raise HTTPException(422,'Choose one of the prediction answers.')
        correct=video_quiz.record_answer(up,video_quiz.questions(unit)[-1],body.option)
        save(who,record,progress)
        return {'correct':correct,'feedback':question['explanation'],'actual_output':question['verification']['output'],'learning':public_state(record,progress)}

    @app.post('/api/video-learning/quiz')
    async def quiz_answer(body: QuizInput,request: Request):
        who=owner(request,True);busy(who);record,progress,unit=current(who,body);up=unit_progress(progress,unit['id'])
        if up['phase']!='prediction':raise HTTPException(409,'Reopen the quick quiz before answering. Your coding work is saved.')
        question=next((q for q in video_quiz.questions(unit) if q['id']==body.question_id),None)
        if not question or question['question_hash']!=body.question_hash:raise HTTPException(409,'This quiz changed. Refresh before answering.')
        if body.option>=len(question['options']):raise HTTPException(422,'Choose one of this question’s options.')
        correct=video_quiz.record_answer(up,question,body.option);save(who,record,progress)
        return {'correct':correct,'feedback':question['explanation'],'learning':public_state(record,progress)}

    @app.post('/api/video-learning/quiz/prepare')
    async def prepare_quiz(body: QuizPrepareInput,request: Request):
        who=owner(request,True);busy(who);record,progress,unit=current(who,body);up=unit_progress(progress,unit['id'])
        if unit.get('quiz'):return {'learning':public_state(record,progress),'allowance':store.provider_allowance()}
        if up['phase']!='prediction' or up['active_activity']!='practice':raise HTTPException(409,'Open this concept’s quick quiz first.')
        if not body.consent or not meta.enabled:raise HTTPException(409,'Allow Meta processing before adding lesson checks.')
        if not execution.ready:raise HTTPException(503,'Python is warming up. Your existing lesson is saved.')
        chunks=passages(record,unit['title']+' '+unit['explanation'],unit);source_ids=[c['id'] for c in chunks]
        evidence={'concept':unit['title'],'explanation':unit['explanation'],'caption_excerpts':chunks,'allowed_passage_ids':source_ids,'existing_prediction':unit['prediction']['code'],
            'learner_preferences':coach.teaching_preferences(who) if coach else {}}
        instruction='''Create ONE short original optional quiz question about this specific lesson explanation before its output prediction. Do not copy an external course. Choose a concept question or a tiny code-completion question with exactly one ___ placeholder. Put any concrete Python example in code, never an assignment or collection literal in the prose prompt. For concept, expected_output must be empty and code may be empty if no premise is needed; otherwise include a complete runnable setup without errors. Quote string literals in lists/dictionaries with single or double quotes; bare names must be defined variables, not unquoted text. Use three or four distinct single-line options and answer_index, a brief explanation for feedback after the attempt, and only supplied source IDs. For complete_code exactly one substituted option must print expected_output. Supported code: simple values, lists, dictionaries, assignments, print/len/range, if, for/while, break/continue, basic subscripts and get/keys/values/items/append. No imports, input, classes, annotations, comprehensions, private names or host operations. Keep under 12 code lines. Test the mental model; do not give a solution to the function exercise. A quiz answer is not evidence of mastery.'''
        instruction+='\n'+QUALITY_INSTRUCTION
        generating.add(who);last_error=None
        try:
            for attempt in range(2):
                request_evidence=evidence|({'repair_request':last_error} if last_error else {})
                reserve_cloud(who,True,'Meta optional lesson quiz'+(' repair' if attempt else ''))
                try:
                    result=await meta.generate(instruction,request_evidence,source_ids,schema=source_schema(QuizBatch,source_ids),max_completion_tokens=1800,call_context={'session_id':record['lesson_id']})
                    anchors=grounding.verify(result,chunks)
                    async with semaphore:checked=await validate_quiz(result['quiz'],execution,source_ids)
                    break
                except MetaUnavailable as error:
                    if error.kind!='execution_check':raise
                    last_error=str(error)[:500]
                except (ValueError,KeyError,TypeError) as error:last_error='The quiz did not match the supported format.' if isinstance(error,SpecError) else str(error)[:500]
            else:raise ValueError('The new quiz could not be checked. Your lesson and code are unchanged.')
            session_key='hub_session' if record.get('context')=='hub' else 'youtube_session'
            latest_record=store.progress(who).get(session_key)
            if not latest_record or latest_record.get('lesson_id')!=record['lesson_id']:raise HTTPException(409,'The video lesson changed while the quiz was being prepared. The new lesson was kept.')
            target=next((u for u in latest_record['curriculum']['units'] if u['id']==unit['id']),None)
            if not target:raise HTTPException(409,'This concept changed while the quiz was being prepared.')
            target['quiz']=checked;target['quiz_model']=result['model'];target['quiz_evidence_quotes']=anchors;store.set_progress(who,session_key,latest_record)
            if coach:coach.remember(who,latest_record)
            latest=store.progress(who).get(progress_key(record['lesson_id'])) or progress
            return {'learning':public_state(latest_record,latest),'allowance':store.provider_allowance()}
        except (ValueError,MetaUnavailable) as error:raise HTTPException(503,str(error)) from None
        finally:generating.discard(who)

    @app.post('/api/video-learning/move')
    async def move(body: MoveInput,request: Request):
        who=owner(request,True);record,progress,unit=current(who,lesson_id=body.lesson_id)
        if record['lesson_id']!=body.lesson_id:raise HTTPException(409,'The video lesson changed. Refresh before continuing.')
        transition_hash=digest(json.dumps({'unit':body.unit_id,'action':body.action,'review':body.review_unit_id},sort_keys=True))
        previous=next((t for t in progress['transitions'] if body.request_id and t['id']==body.request_id),None)
        if previous:
            if previous['input_hash']!=transition_hash:raise HTTPException(409,'This transition identifier was already used for a different action.')
            return {'learning':public_state(record,progress),'allowance':store.provider_allowance()}
        busy(who)
        if unit['id']!=body.unit_id:raise HTTPException(409,'The active concept changed. Refresh before continuing.')
        up=unit_progress(progress,unit['id'])
        if record.get('course_flow')=='lesson-first' and up['phase']=='lesson' and body.action!='quiz':raise HTTPException(409,'Open the teaching lesson, then start its topic check before coding.')
        if body.action=='practice':
            if not video_quiz.ready(unit,up):raise HTTPException(409,'Finish the quick quiz or choose Skip to coding.')
            if up['active_activity']!='practice':raise HTTPException(409,'Return from the current exercise before opening main practice.')
            up['phase']='exercise';up['last_run_id']=up['activities']['practice']['last_run_id']
        elif body.action=='skip_quiz':
            if up['active_activity']!='practice' or progress.get('review_resume'):raise HTTPException(409,'Finish or return from the current activity first.')
            up['quiz_skipped']=True;up['phase']='exercise';up['last_run_id']=up['activities']['practice']['last_run_id']
        elif body.action=='quiz':
            if up['active_activity']!='practice' or progress.get('review_resume'):raise HTTPException(409,'Quick quizzes are available beside the main practice task.')
            up['phase']='prediction';up['last_run_id']=None;up['lesson_opened']=True
        elif body.action=='return_practice':
            if adaptive.active(up)['kind']!='simpler' or not adaptive.active(up)['passed']:raise HTTPException(409,'Finish this smaller step before returning to the main exercise.')
            up['active_activity']='practice';up['last_run_id']=up['activities']['practice']['last_run_id'];up['phase']='exercise'
        elif body.action in {'fresh_check','review'}:
            if body.action=='fresh_check' and record.get('context')=='course' and not video_quiz.assessment_ready(unit,up):raise HTTPException(409,'Finish every topic-check question correctly before the independent task. You can revisit questions after coding.')
            frozen=body.action=='fresh_check' and record.get('context')=='course' and unit.get('fresh_exercise') and not any(v.get('frozen') for v in up['variants'].values())
            if not body.consent and not frozen:raise HTTPException(409,'Allow Meta processing to create this new exercise.')
            if not body.request_id:raise HTTPException(422,'Refresh the page before requesting a new exercise.')
            if not execution.ready:raise HTTPException(503,'Python is warming up. Existing work is saved.')
            target=unit;target_up=up;kind='review' if progress.get('review_resume') else 'fresh'
            if body.action=='review':
                if progress.get('review_resume'):raise HTTPException(409,'Return to your lesson before starting another review.')
                target=next((u for u in record['curriculum']['units'] if u['id']==body.review_unit_id),None)
                if not target:raise HTTPException(422,'Choose a concept from this lesson for review.')
                target_up=unit_progress(progress,target['id']);kind='review'
                if not target_up['independent_passed'] or not target_up['review_due_at'] or target_up['review_due_at']>time.time():
                    raise HTTPException(409,'That concept’s later review is not due yet. You can continue normal practice.')
            elif not adaptive.active(up)['passed'] or not up['practice_passed']:
                raise HTTPException(409,'Finish the main practice checks before requesting a fresh task.')
            generating.add(who)
            try:created=await variant(who,target,target_up,record,kind)
            finally:generating.discard(who)
            # Merge new work into the latest progress, preserving any completed Python job.
            progress=store.progress(who).get(progress_key(record['lesson_id'])) or progress
            adaptive.upgrade(progress,record['curriculum']['units'])
            target_up=unit_progress(progress,target['id'])
            if body.action=='review':
                progress['review_resume']={'index':progress['current_unit'],'complete':progress['complete'],'activity':target_up['active_activity'],'phase':target_up['phase']}
                progress['current_unit']=next(i for i,u in enumerate(record['curriculum']['units']) if u['id']==target['id']);progress['complete']=False
            adaptive.activate(target_up,created)
            progress['messages'].append({'role':'assistant','text':('Try this smaller step.' if kind=='simpler' else 'Try this new task without tutor hints first. You can still run and visualise your own code. Asking for help is always available and will be recorded as supported practice.'),'follow_up':created['opening_question'] if kind=='simpler' else '','sources':created['exercise']['sources'],'unit_id':target['id'],'at':time.time(),'kind':'activity_transition'})
        elif body.action=='resume':
            resume=progress.pop('review_resume',None)
            if not resume:raise HTTPException(409,'No later review is open.')
            up['active_activity']=resume['activity'];up['phase']=resume['phase'];up['last_run_id']=adaptive.active(up)['last_run_id']
            progress['current_unit']=resume['index'];progress['complete']=resume['complete']
        else:
            if progress.get('review_resume'):raise HTTPException(409,'Return from the review before moving to another concept.')
            if record.get('course_flow')=='lesson-first':
                if not up.get('lesson_opened') or not up['practice_passed']:raise HTTPException(409,'Study the lesson and pass its main practice checks before moving on.')
            elif not up['independent_passed']:raise HTTPException(409,'Pass a fresh check without recorded tutor help before moving on. Supported practice alone does not unlock the next concept.')
            if record.get('context')=='course' and not video_quiz.assessment_ready(unit,up):raise HTTPException(409,'Complete this topic check correctly before moving on.')
            units=record['curriculum']['units']
            order=[] if record.get('course_flow')=='lesson-first' else list(range(progress['current_unit']+1,len(units)))+list(range(progress['current_unit']))
            remaining=next((i for i in order if not unit_progress(progress,units[i]['id'])['independent_passed']),None)
            if remaining is not None:
                progress['current_unit']=remaining;unit=units[remaining]
                progress['messages'].append({'role':'assistant','text':unit['opening_question'],'follow_up':'','sources':unit['sources'],'unit_id':unit['id'],'at':time.time(),'kind':'opening'})
            else:progress['complete']=True
        if body.request_id:progress['transitions']=(progress['transitions']+[{'id':body.request_id,'input_hash':transition_hash}])[-30:]
        save(who,record,progress)
        return {'learning':public_state(record,progress),'allowance':store.provider_allowance()}

    async def run_job(who,identifier,record,unit,exercise,activity_id,body,arguments,entry):
        try:
            async with semaphore:
                store.finish_run(who,identifier,'running')
                raw=await execution.execute(exercise_payload(exercise,body.source,arguments,body.trace_case) if body.mode=='exercise' else {'source':body.source,'entry':entry,'arguments':arguments,'trace_case':0})
                if raw.get('error') or raw.get('source_sha256')!=digest(body.source) or len(raw.get('cases',[]))!=len(arguments):raise ValueError('Execution provenance mismatch.')
                checks=[]
                if body.mode=='exercise':
                    for i,(case,expected) in enumerate(zip(raw['cases'],exercise['cases'])):
                        checks.append({'input':arguments[i],'expected':expected['expected'],'actual':case.get('actual'),'error':case.get('error'),
                            'passed':case_passed(case,expected['expected'],arguments[i],exercise['preserve_input']),
                            'input_unchanged':case.get('arguments_after')==arguments[i] if exercise['preserve_input'] else None})
                chosen=raw['cases'][body.trace_case if checks else 0]
                skill_requirement=None
                if checks and all(c['passed'] for c in checks) and record.get('context')=='course':
                    from .course_policy import require_target
                    try:require_target(body.source,record['course_concept'],exercise,chosen.get('events',[]))
                    except ValueError as error:skill_requirement=str(error)
                report={'lesson_id':record['lesson_id'],'unit_id':unit['id'],'source':body.source,'source_hash':raw['source_sha256'],'runtime':raw['runtime'],
                    'trace':chosen.get('events',[]),'output':chosen.get('output',''),'actual':chosen.get('actual'),'error':chosen.get('error'),'checks':checks,
                    'all_passed':bool(checks) and all(c['passed'] for c in checks) and not skill_requirement,'origin':body.origin,'video_mode':body.mode,'trace_case':body.trace_case if checks else 0,
                    'skill_requirement':skill_requirement}
                progress=store.progress(who).get(progress_key(record['lesson_id'])) or blank_progress(record)
                saved=store.get_run(who,identifier)
                if saved and saved['status']=='cancelled':return
                up=unit_progress(progress,unit['id'])
                if body.mode=='exercise':adaptive.observe_run(up,identifier,report,activity_id)
                else:
                    up['last_run_id']=identifier
                    if not up['prediction_ok']:up['viewed_execution']=True
                store.finish_run(who,identifier,'complete',report)
                save(who,record,progress)
        except asyncio.CancelledError:store.cancel_run(who,identifier);raise
        except Exception:store.finish_run(who,identifier,'failed',{'error':{'type':'RunnerUnavailable','message':'The Python run could not finish within the supported limits.'}})
        finally:tasks.pop(identifier,None)

    @app.post('/api/video-learning/run')
    async def run(body: RunInput,request: Request):
        who=owner(request,True);busy(who);record,progress,unit=current(who,body);up=unit_progress(progress,unit['id']);exercise=adaptive.exercise_for(unit,up)
        if not execution.ready:raise HTTPException(503,'Python is warming up.')
        if len(tasks)>=6:raise HTTPException(429,'Wait for the current Python runs to finish.')
        if body.mode=='exercise' and up['phase']!='exercise':raise HTTPException(409,'Open the practice task after checking your prediction.')
        if body.mode=='exercise':check_activity(up,body.activity_id)
        if body.mode=='prediction' and body.source!=unit['prediction']['code']:raise HTTPException(409,'Use exploration mode for an edited prediction snippet.')
        arguments=[c['arguments'] for c in exercise['cases']] if body.mode=='exercise' else [[]]
        if body.trace_case>=len(arguments):raise HTTPException(422,'Choose one of this task’s checks.')
        entry=exercise['entry'] if body.mode=='exercise' and exercise.get('kind','function')=='function' else None
        try:
            validate(body.source,entry)
            if body.mode=='exercise' and record.get('context')=='course':
                from . import course_policy
                course_policy.check_code(body.source,record['course_concept'])
        except (ValueError,SyntaxError) as error:raise HTTPException(422,str(error)[:300]) from None
        identifier=store.create_run(who,'video:'+record['lesson_id']+':'+unit['id']+':'+body.mode,body.source,digest(body.source))
        tasks[identifier]=asyncio.create_task(run_job(who,identifier,record,unit,exercise,up['active_activity'],body,arguments,entry))
        return {'id':identifier,'status':'queued'}

    @app.post('/api/video-learning/coach')
    async def tutor(body: ChatInput,request: Request):
        who=owner(request,True);record,progress,unit=current(who,body)
        input_hash=digest(json.dumps(body.model_dump(exclude={'consent'}),sort_keys=True))
        previous=next((m for m in progress['messages'] if m.get('request_id')==body.request_id and m['role']=='assistant'),None)
        if previous:
            if previous.get('input_hash')!=input_hash:raise HTTPException(409,'This message identifier was already used for a different reply.')
            return {'message':{k:v for k,v in previous.items() if k not in {'input_hash','request_id'}},'learning':public_state(record,progress),'allowance':store.provider_allowance()}
        busy(who)
        if not body.consent:raise HTTPException(409,'Allow Meta to process your question and selected lesson context first.')
        up=unit_progress(progress,unit['id']);check_activity(up,body.activity_id)
        activity_id=up['active_activity'];report=None
        if body.run_id:
            saved=store.get_run(who,body.run_id)
            if not saved or saved['status']!='complete' or saved['source']!=body.source or saved['report'].get('lesson_id')!=record['lesson_id'] or saved['report'].get('unit_id')!=unit['id']:
                raise HTTPException(409,'Run this exact code in this lesson before asking about its trace.')
            report=saved['report']
            if report.get('video_mode')=='exercise' and report.get('activity_id','practice')!=activity_id:
                raise HTTPException(409,'That trace belongs to another exercise. Run this task first.')
        chunks=passages(record,body.text+' '+unit['title'],unit);source_ids=[c['id'] for c in chunks]
        quiz_context=None
        if up['phase']=='prediction' and body.quiz_question_id:
            question=next((q for q in video_quiz.questions(unit) if q['id']==body.quiz_question_id),None)
            if not question:raise HTTPException(409,'That quiz question changed. Refresh the lesson.')
            quiz_context=video_quiz.public_question(question)
        recent=[{'role':m['role'],'text':m['text'][:650],'follow_up':m.get('follow_up','')[:300]} for m in progress['messages'][-6:]]
        trace=report.get('trace',[]) if report else []
        actions=adaptive.eligible_actions(up,report,body.text,body.intent)
        if record.get('course_flow')=='lesson-first':actions=[a for a in actions if a not in {'simpler_practice','fresh_check','research_topic'}]
        if record.get('context')=='course' and not video_quiz.assessment_ready(unit,up):actions=[a for a in actions if a!='fresh_check']
        if up['phase']!='exercise':actions=[a for a in actions if a not in {'simpler_practice','fresh_check'}]
        if coach and coach.can_research(who,record,unit,up,chat=True):actions.append('research_topic')
        evidence={'learner_message':body.text,'intent':body.intent,'concept':unit['title'],'concept_explanation':unit['explanation'],'current_code':body.source,
            'current_activity':up['phase'],'activity_kind':adaptive.active(up)['kind'],'previous_help_count':up['hint_count'],
            'task':adaptive.exercise_for(unit,up)['instructions'],'checked':bool(report),'observed_checks':report.get('checks',[]) if report else [],
            'selected_step':trace[min(body.step,len(trace)-1)] if trace else None,'selected_step_index':min(body.step,len(trace)-1) if trace else None,
            'trace_summary':[{'index':i,'line':e['line'],'kind':e['kind'],'error':e.get('error')} for i,e in enumerate(trace)],
            'learner_expectation':adaptive.active(up)['learner_expectation'],'recent_attempts':up['attempt_history'][-4:],
            'available_actions':actions,'recent_conversation':recent,'caption_excerpts':chunks}
        evidence['quiz_question']=quiz_context;evidence['quiz_progress']=video_quiz.status(unit,up)
        evidence['learner_preferences']=coach.teaching_preferences(who) if coach else {}
        if record.get('context')=='course':evidence['concept_id']=record['course_concept']
        evidence['help_level']=adaptive.active(up).get('help_level',0)
        evidence['skill_requirement']=report.get('skill_requirement') if report else None
        tutor_instruction=adaptive.COACH_INSTRUCTION
        if record.get('context')=='course':
            from .course_policy import instruction as concept_instruction
            evidence['course_prerequisite_policy']=concept_instruction(record['course_concept'])
            tutor_instruction+='\n'+evidence['course_prerequisite_policy']
            task=adaptive.exercise_for(unit,up);evidence['practice_format']=task.get('kind','function');evidence['supplied_input_names']=task.get('parameters',[])
            evidence['sample_supplied_inputs']=dict(zip(task.get('parameters',[]),task['cases'][0]['arguments'])) if task.get('kind')=='program' else None
        evidence['help_focus']=['Ask about the approach or offer a small conceptual nudge.','Give a more concrete clue about the relevant operation without writing the answer.','Prefer an observed trace step or source explanation over another generic hint.','Offer a smaller step when eligible, otherwise inspect actual evidence.'][min(evidence['help_level'],3)]
        if len(json.dumps(evidence))>24000:raise HTTPException(422,'Use a shorter code example or question for this tutor request.')
        schema=adaptive.decision_schema(actions,source_ids)
        reserve_cloud(who,True,'adaptive current-video teaching decision');chatting.add(who)
        created=None
        try:
            answer=await meta.generate(tutor_instruction,evidence,source_ids,schema=schema,max_completion_tokens=2600,call_context={'session_id':record['lesson_id']})
            validate_response({k:answer[k] for k in schema['properties']},schema)
            answer['evidence_quotes']=grounding.verify(answer,chunks)
            if record.get('context')=='course':
                from .course_policy import check_text
                check_text(answer['answer']+'\n'+answer['follow_up'],record['course_concept'])
            adaptive.reject_repeated_hint(progress['messages'],activity_id,answer,body.text)
            inline=re.findall(r'\[((?:video|hub)-[A-Za-z0-9_-]+)\]',answer['answer']+' '+answer['follow_up'])
            if any(identifier not in source_ids for identifier in inline):raise ValueError('Meta cited a source outside this lesson context.')
            action=answer['action'];result={'kind':action,'reason':answer['reason']}
            if action=='review_source':
                source=next(c for c in chunks if c['id']==answer['source_id'])
                result|={'source_id':source['id'],'excerpt':source['text'][:900],'start':source['start']}
            elif action=='inspect_trace':
                if not trace or answer['trace_step']>=len(trace):raise ValueError('Meta selected a trace step that was not observed.')
                result|={'run_id':body.run_id,'step':answer['trace_step'],'line':trace[answer['trace_step']]['line']}
            elif action=='research_topic':
                try:
                    research=coach.research(who,record['lesson_id'],unit['id'],automatic=True)
                    result|={'job_id':research['job']['id']}
                    answer['answer']='I’m preparing one focused Loops follow-up using the research permission you enabled. Your current lesson and code stay saved. Check Next useful step for its result.'
                except HTTPException as error:
                    answer['answer']='The research could not start: '+str(error.detail)+'. Your current exercise is saved.'
                answer['follow_up']=''
            elif action in {'simpler_practice','fresh_check'}:
                if not execution.ready:raise ValueError('Python is warming up. Your current exercise is saved.')
                kind='simpler' if action=='simpler_practice' else 'review' if progress.get('review_resume') else 'fresh'
                created=await variant(who,unit,up,record,kind)
                result|={'activity_id':created['id'],'activity_kind':created['kind']}
                # Publish the validated task contract, not the planner's imagined task.
                answer['answer']='### '+created['exercise']['title']+'\n\n'+created['exercise']['instructions']
                answer['follow_up']=created['opening_question'] if kind=='simpler' else ''
                answer['sources']=created['exercise']['sources']
                answer['evidence_quotes']=created['exercise'].get('evidence_quotes',[])
                answer['claim_review']=created['exercise'].get('claim_review')
        except ValidationError:raise HTTPException(503,'Meta chose an unavailable teaching action. Your current exercise was kept.') from None
        except (MetaUnavailable,ValueError,KeyError) as error:
            if getattr(meta,'last_failure',None):(store.path.parent/'adaptive-last-provider-error.json').write_text(json.dumps(meta.last_failure),encoding='utf-8')
            raise HTTPException(503,str(error)[:600]) from None
        finally:chatting.discard(who)
        progress=store.progress(who).get(progress_key(record['lesson_id'])) or progress
        adaptive.upgrade(progress,record['curriculum']['units']);up=unit_progress(progress,unit['id']);state=up['activities'][activity_id]
        if re.search(r'\b(expect|expected|thought|wanted)\b',body.text,re.I) or body.intent=='reply' and state['expectation_requested']:state['learner_expectation']=body.text[:500]
        if answer['action']=='ask_expectation':state['expectation_requested']=True
        state['help_level']=min(3,state.get('help_level',0)+1)
        # A successful tutor response is recorded as help for the task it discussed.
        if up['phase']=='exercise':state['supported']=True
        if created:adaptive.activate(up,created)
        user={'role':'user','text':body.text,'unit_id':unit['id'],'activity_id':activity_id,'at':time.time(),'request_id':body.request_id}
        assistant={'role':'assistant','text':answer['answer'],'follow_up':answer['follow_up'],'sources':answer['sources'],'unit_id':unit['id'],
            'at':time.time(),'request_id':body.request_id,'input_hash':input_hash,'model':answer['model'],'action_result':result,'evidence_quotes':answer.get('evidence_quotes',[]),'claim_review':answer.get('claim_review'),'activity_id':activity_id}
        progress['messages']=(progress['messages']+[user,assistant])[-60:];up['hint_count']+=1
        up['decisions']=(up['decisions']+[{'action':answer['action'],'reason':answer['reason'],'activity_id':activity_id,'run_id':body.run_id,'at':time.time()}])[-30:]
        save(who,record,progress)
        return {'message':{k:v for k,v in assistant.items() if k not in {'input_hash','request_id'}},'learning':public_state(record,progress),'allowance':store.provider_allowance()}
