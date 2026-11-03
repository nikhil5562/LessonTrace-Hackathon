"""Shared frozen content, owned evidence, and rule-triggered concept extras."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import time
import uuid

from fastapi import HTTPException,Request
from pydantic import BaseModel,Field

from . import adaptive,course_policy,video_quiz
from .course_catalog import COURSE,VERSION,UNITS,TOPICS,outline,topic,allowed_concepts,graph_digest
from .course_agent import CourseAgent
from .course_sources import loader as source_loader
from .course_placement import PLACEMENT,artifact as placement_artifact
from .video_curriculum import validate_exercise,validate_quiz,QuizQuestion,checked_run
from .video_lessons import public_session
from .meta import MetaUnavailable

ROOT=Path(__file__).resolve().parents[2]


def key(identifier):return 'video_progress_'+identifier
def defaults():return {'version':VERSION,'revision':0,'lessons':{},'evidence':{},'extras':{},'auto_hub':False,'legacy_lessons':{}}


class OpenTopic(BaseModel):
    concept_id:str=Field(max_length=40)


class OpenEarlier(BaseModel):
    lesson_id:str=Field(pattern=r'^[a-f0-9]{32}$')


class Permission(BaseModel):
    revision:int=Field(ge=0)
    enabled:bool
    consent:bool=False


class ExtraInput(BaseModel):
    concept_id:str=Field(max_length=40)
    lesson_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    consent:bool=False
    reason:str=Field(default='practice',pattern=r'^(notes|practice|debug)$')
    retry:bool=False


class CourseService:
    def __init__(self,store,meta,execution,reserve,tasks,semaphore,*,content_root=None,source_reader=None):
        self.store,self.meta,self.execution,self.reserve,self.tasks,self.semaphore=store,meta,execution,reserve,tasks,semaphore
        self.content_root=Path(content_root or ROOT/'course_content'/VERSION)
        self.agent=CourseAgent(meta,execution,source_reader or source_loader(store.path.parent/'course-source-cache'),reserve,semaphore)

    def state(self,who):
        progresses=self.store.progress(who);state=progresses.get('course_state') or defaults()
        if state.get('version')=='python-fundamentals-v1' and VERSION!=state['version']:
            previous=copy.deepcopy(state);carried={}
            for concept,evidence in state.get('evidence',{}).items():
                record=self.store.saved_lesson(who,evidence.get('lesson_id'));progress=progresses.get(key(evidence.get('lesson_id','')))
                run=self.store.get_run(who,evidence.get('independent_run_id')) if evidence.get('independent_run_id') else None
                if not record or not progress or not run or not (run.get('report') or {}).get('independent_check'):continue
                unit=record['curriculum']['units'][0];up=adaptive.unit_state(progress,unit['id'])
                if concept in TOPICS and up['independent_passed'] and video_quiz.assessment_ready(unit,up):carried[concept]={**evidence,'version':VERSION,'previous_version':state['version'],'basis':'Verified earlier topic/independent checks retained as prerequisite evidence; not a mastery claim.'}
            def migrate(current):
                if current.get('version')==VERSION:return
                current.clear();current.update(defaults());current['evidence']=carried;current['legacy_lessons']=previous.get('lessons',{})
            state=self.store.mutate_progress(who,'course_state',defaults(),migrate)
            self.store.set_progress(who,'course_previous_python-fundamentals-v1',previous)
        return state
    def change(self,who,fn):return self.store.mutate_progress(who,'course_state',defaults(),fn)
    def demonstrated(self,who):return {identifier for identifier,item in self.state(who)['evidence'].items() if item.get('version')==VERSION and identifier in TOPICS}

    def completion(self,who,identifier,progresses):
        """Explain remaining work without changing grading or awarding evidence."""
        record=self.store.saved_lesson(who,identifier) if identifier else None
        if not record or record.get('course_version')!=VERSION:return None
        progress=progresses.get(key(identifier))
        if not progress:return None
        unit=record['curriculum']['units'][0];up=adaptive.unit_state(progress,unit['id']);active=adaptive.active(up)
        quiz=video_quiz.status(unit,up);correct=sum(bool(q.get('correct')) for q in quiz['items'])
        practice=up['activities']['practice'];saved=self.store.get_run(who,practice.get('last_run_id')) if practice.get('last_run_id') else None
        checks=(saved.get('report') or {}).get('checks',[]) if saved and saved['status']=='complete' else []
        ready=video_quiz.assessment_ready(unit,up)
        if record.get('course_flow')=='lesson-first':
            opened=up.get('lesson_opened',False);passed=opened and ready and up['practice_passed']
            stage='complete' if passed else 'lesson' if not opened else 'quiz' if not ready else 'practice'
            message='Lesson, topic/debug check and coding task passed. Open the next lesson.' if passed else 'Read the teaching lesson, then start its topic and debugging check.' if not opened else f'Complete the topic/debug check: {correct} of {quiz["total"]} answers correct.' if not ready else f'Main practice: {sum(c["passed"] for c in checks)} of {len(checks)} checks passed. Ask Meta for a hint or explanation on this task.' if checks else 'Topic check passed. Complete the coding task to unlock the next lesson.'
            return {'stage':stage,'message':message,'quiz_correct':correct,'quiz_total':quiz['total'],'practice_passed':up['practice_passed'],
                'practice_checks_passed':sum(c['passed'] for c in checks),'practice_checks_total':len(checks),'independent_passed':up['independent_passed'],
                'independent_required':False,'lesson_opened':opened,'activity_kind':active['kind']}
        stage='complete' if up['independent_passed'] and ready else 'quiz' if not ready else 'practice' if not up['practice_passed'] else 'independent'
        if stage=='complete':message='Topic check, main practice and independent task passed.'
        elif stage=='quiz':message=f'Complete the topic check: {correct} of {quiz["total"]} answers correct.'
        elif stage=='practice':
            message=f'Main practice: {sum(c["passed"] for c in checks)} of {len(checks)} checks passed. Fix the remaining checks, then try the independent task.' if checks else 'Topic check passed. Run the main practice, then try the independent task.'
        elif active['kind'] in {'fresh','review'} and active['supported']:message='This task has recorded tutor help. Pass it, then try another independent task.'
        elif active['kind'] in {'fresh','review'}:message='Main practice passed. Finish the independent task without tutor hints.'
        else:message='Main practice passed. Open the independent task to finish this concept.'
        return {'stage':stage,'message':message,'quiz_correct':correct,'quiz_total':quiz['total'],
            'practice_passed':up['practice_passed'],'practice_checks_passed':sum(c['passed'] for c in checks),'practice_checks_total':len(checks),
            'independent_passed':up['independent_passed'],'activity_kind':active['kind']}

    def base(self,concept):
        manifest_path=self.content_root/'manifest.json'
        if not manifest_path.is_file():return None
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('version')!=VERSION or manifest.get('status')!='reviewed-pilot':return None
        if manifest.get('graph_hash')!=graph_digest():raise HTTPException(503,'The course prerequisite graph changed. Review and version it before serving its questions.')
        entry=manifest['lessons'].get(concept)
        if not entry:return None
        if entry['file']!=concept+'.json':raise HTTPException(503,'The course manifest needs verification.')
        raw=(self.content_root/entry['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise HTTPException(503,'The frozen course content changed. Existing work is saved; verify the course version before continuing.')
        result=json.loads(raw)
        if result.get('version')!=VERSION or result.get('concept_id')!=concept:raise HTTPException(503,'The frozen concept identity needs verification.')
        from .course_errata import apply
        try:return apply(result,raw)
        except ValueError as error:raise HTTPException(503,str(error)) from None

    def access(self,who,record,unit=None):
        if record.get('context')!='course':return
        concept=record['course_concept'];item=topic(concept);known=self.demonstrated(who)
        missing=set(item['needs'])-known
        if missing:raise HTTPException(409,'Complete the prerequisite checks first: '+', '.join(topic(i)['title'] for i in sorted(missing))+'.')
        if unit:
            up=adaptive.unit_state(self.store.progress(who).get(key(record['lesson_id']),{'units':{}}),unit['id'])
            values=unit.get('quiz',[])+[unit['prediction'],adaptive.exercise_for(unit,up)]
            if any(not course_policy.eligible(value,known) for value in values):raise HTTPException(409,'A question requires an uncompleted concept. Return to the course map before continuing.')

    def signals(self,record,progress):
        unit=record['curriculum']['units'][progress['current_unit']];up=adaptive.unit_state(progress,unit['id']);activity=adaptive.active(up)
        wrong={h['question_id'] for h in up.get('quiz_history',[]) if not h['correct'] and record['course_concept'] in h.get('targets',[])}
        quiet=activity['kind'] in {'fresh','review'} and not activity['independent_run_id']
        failures=up['activities']['practice']['failures']
        return {'wrong_questions':len(wrong),'failed_practice_runs':failures,'concept':record['course_concept'],
            'needs_support':not up['independent_passed'] and not quiet and (len(wrong)>=2 or failures>=2),'quiet':quiet,
            'rule':'Two distinct wrong questions targeting this concept, or two unsuccessful practice runs. No inference from time spent or personality.'}

    def observe(self,who,record,progress):
        if record.get('context')!='course':return
        self.store.save_lesson(who,record)
        if record.get('course_version')!=VERSION:return
        unit=record['curriculum']['units'][0];up=adaptive.unit_state(progress,unit['id']);concept=record['course_concept']
        taught=record.get('course_flow')=='lesson-first'
        passed=(up.get('lesson_opened') and up['practice_passed']) if taught else up['independent_passed']
        if record.get('course_role') in {'base','placement'} and passed and video_quiz.assessment_ready(unit,up):
            evidence={'version':VERSION,'lesson_id':record['lesson_id'],'independent_run_id':next((a['independent_run_id'] for a in up['activities'].values() if a['independent_run_id']),None),
                'at':time.time(),'basis':'Current version topic questions correct and a different task passed without recorded tutor help. Not a mastery certification.'}
            if taught:evidence.update(main_run_id=up['activities']['practice']['last_run_id'],supported=up['activities']['practice']['supported'],basis='Lesson opened, topic/debug questions correct and coding checks passed. Tutor help is allowed and recorded; this is not an independent or mastery claim.')
            self.change(who,lambda state:state['evidence'].setdefault(concept,evidence))
        signals=self.signals(record,progress)
        if record.get('course_role')=='base' and (not taught or passed) and self.state(who)['auto_hub'] and signals['needs_support'] and concept not in self.state(who)['extras']:
            try:self.begin_extra(who,record,signals,automatic=True)
            except HTTPException as error:
                self.change(who,lambda state:state.update(last_research_error=str(error.detail)[:260]))

    def extra_public(self,who,concept,entry):
        result={k:v for k,v in entry.items() if k in {'id','status','message','lesson_id','parent_id','created','automatic','reason','opened','attempts'}}
        task_id='course:'+who+':'+entry['id']
        if entry['status'] in {'queued','running'} and task_id not in self.tasks:
            def interrupted(state):state['extras'][concept].update(status='failed',message='The follow-up was interrupted. Your course lesson is saved.')
            self.change(who,interrupted);result.update(status='failed',message='The follow-up was interrupted. Your course lesson is saved.')
        return result

    def catalog(self,who):
        state=self.state(who);known=self.demonstrated(who);units=copy.deepcopy(outline());items=[];progresses=self.store.progress(who)
        for unit in units:
            for concept in unit['topics']:
                frozen=self.base(concept['id'])
                missing=set(concept['needs'])-known
                concept.update(demonstrated=concept['id'] in known,missing_needs=sorted(missing),available=not missing and bool(frozen or concept['id'] in PLACEMENT),
                    content='pilot_lesson' if frozen else 'placement_check' if concept['id'] in PLACEMENT else 'outline',lesson_id=state['lessons'].get(concept['id']),
                    completion=self.completion(who,state['lessons'].get(concept['id']),progresses))
                items.append(concept)
            unit['lesson_count']=sum(c['content']=='pilot_lesson' for c in unit['topics']);unit['complete_content']=unit['lesson_count']==len(unit['topics'])
        extra={c:self.extra_public(who,c,e) for c,e in state['extras'].items()};active=self.store.progress(who).get('course_session');signals=None
        if active and self.store.progress(who).get(key(active['lesson_id'])):signals=self.signals(active,self.store.progress(who)[key(active['lesson_id'])])
        return {'course':COURSE,'units':units,'demonstrated':sorted(known),'evidence':state['evidence'],'revision':state['revision'],'auto_hub':state['auto_hub'],
            'extras':extra,'signals':signals,'active_lesson_id':active['lesson_id'] if active else None,'allowance':self.store.provider_allowance(),'meta_enabled':self.meta.enabled,
            'next_concept':next((c['id'] for c in items if c['available'] and not c['demonstrated']),None),
            'lesson_count':sum(u['lesson_count'] for u in units),'earlier_lessons':[{'id':identifier,'concept_id':concept,'title':topic(concept)['title']} for concept,identifier in state.get('legacy_lessons',{}).items() if concept in TOPICS],
            'scope':'Source-linked teaching lessons, topic/debug questions and coding checks. Passing unlocks the next concept; extra practice is optional afterward.'}

    def record(self,artifact,identifier,role,*,parent_id=None):
        if artifact.get('flow')=='lesson-first' and role=='placement':role='base'
        concept=artifact['concept_id'];chunks=artifact['caption_chunks'];video=next((d for d in artifact['source_documents'] if d['kind']=='video'),None)
        video_id='-7xg8pGcP6w'
        if video and 'v=' in video['url']:video_id=video['url'].split('v=')[1][:11]
        return {'context':'course','course_version':VERSION,'course_flow':artifact.get('flow'),'course_concept':concept,'course_unit':topic(concept)['unit_id'],'course_role':role,'course_parent':parent_id,
            'lesson_id':identifier,'interactive':True,'title':artifact['curriculum']['title'],'answer':artifact['curriculum']['answer'],'sources':artifact['curriculum']['sources'],
            'curriculum':copy.deepcopy(artifact['curriculum']),'caption_chunks':chunks,'source_documents':artifact['source_documents'],'video_id':video_id,
            'url':next((d['url'] for d in artifact['source_documents'] if d['kind']=='web'),'https://docs.python.org/3/tutorial/'),
            'caption_source':'Frozen original course lesson with short source anchors' if role!='placement' else 'Original prerequisite assessment',
            'model':artifact.get('model'),'provider':artifact.get('provider'),'claim_review':artifact['curriculum'].get('claim_review'),'course_wording_revision':artifact.get('course_wording_revision'),'language':'en','auto_generated':False,'created':time.time(),
            'coverage':'Selected cited text and creator-published captions. No independent audio or frame analysis.' if role!='placement' else 'Original placement check; not a generated lesson.',
            'course_review':'Operator-reviewed base' if role=='base' else 'Automatically checked extra; not human-reviewed' if role=='extra' else 'Authored prerequisite check'}

    def teaching_record(self,who,record):
        if record and record.get('course_version')==VERSION and record.get('course_flow')=='lesson-first' and record.get('course_role')=='placement':
            record.update(course_role='base',caption_source='Frozen original course lesson with short source anchors',
                coverage='Selected cited text and creator-published captions. No independent audio or frame analysis.',course_review='AI-assisted operator-reviewed base')
            self.store.save_lesson(who,record)
        if record and record.get('course_version')==VERSION and record.get('course_role')=='base' and not record.get('course_legacy'):
            from .course_errata import PATCHES,update_record
            if record['course_concept'] in PATCHES:
                artifact=self.base(record['course_concept'])
                if artifact and artifact.get('course_wording_revision')!=record.get('course_wording_revision'):
                    record=update_record(record,artifact);self.store.save_lesson(who,record)
                from .course_errata import update_variants
                saved=self.store.progress(who).get(key(record['lesson_id']))
                if saved:
                    fixed=update_variants(saved,record)
                    if fixed!=saved:self.store.set_progress(who,key(record['lesson_id']),fixed)
        return record

    async def open(self,who,concept):
        try:item=topic(concept)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        known=self.demonstrated(who);missing=set(item['needs'])-known
        if missing:raise HTTPException(409,'Complete these concept checks first: '+', '.join(topic(i)['title'] for i in sorted(missing))+'.')
        identifier=self.state(who)['lessons'].get(concept);record=self.store.saved_lesson(who,identifier) if identifier else None
        if record and record.get('course_version')==VERSION:
            record=self.teaching_record(who,record);self.store.set_progress(who,'course_session',record);return public_session(record)
        artifact=self.base(concept)
        if artifact is None:
            if concept not in PLACEMENT:raise HTTPException(409,'This topic is outlined, but its reviewed base lesson is not available in this pilot.')
            if not self.execution.ready:raise HTTPException(503,'Python is warming up before checking this prerequisite task.')
            artifact=placement_artifact(concept)
            async with self.semaphore:
                for field in ('exercise','fresh_exercise'):
                    original=artifact['curriculum']['units'][0][field];checked=await validate_exercise(original,self.execution,artifact['curriculum']['sources']);checked.update({k:original[k] for k in ('needs','targets')});artifact['curriculum']['units'][0][field]=checked
                unit=artifact['curriculum']['units'][0];originals=unit['quiz']
                unit['quiz']=await validate_quiz([{k:v for k,v in q.items() if k in QuizQuestion.model_fields} for q in originals],self.execution,artifact['curriculum']['sources'])
                for original,checked in zip(originals,unit['quiz']):checked.update({k:original[k] for k in ('needs','targets','purpose')})
                prediction=unit['prediction'];actual=await checked_run(self.execution,prediction['code'],None,[[]]);observed=actual['cases'][0]
                output=observed['error']['type'] if observed.get('error') else observed.get('output','').strip()
                if output!=prediction['expected_output'] or prediction['options'].count(output)!=1:raise HTTPException(503,'The prerequisite prediction did not match Python. It was not published.')
                prediction['answer_index']=prediction['options'].index(output);prediction['verification']={'output':output,'runtime':actual['runtime'],'source_hash':actual['source_sha256']}
        record=self.record(artifact,uuid.uuid4().hex,'base' if item['pilot'] else 'placement')
        from .video_learning import blank_progress
        self.store.save_lesson(who,record);self.store.set_progress(who,'course_session',record);self.store.set_progress(who,key(record['lesson_id']),blank_progress(record))
        self.change(who,lambda state:state['lessons'].update({concept:record['lesson_id']}))
        return public_session(record)

    def begin_extra(self,who,record,signals,*,automatic=False,reason='practice',retry=False):
        if record.get('course_role')!='base':raise HTTPException(409,'Hub follow-ups attach to a base course lesson.')
        concept=record['course_concept'];self.access(who,record,record['curriculum']['units'][0]);state=self.state(who)
        if record.get('course_flow')=='lesson-first':
            progress=self.store.progress(who).get(key(record['lesson_id']));unit=record['curriculum']['units'][0];up=adaptive.unit_state(progress,unit['id'])
            if not up['practice_passed'] or not video_quiz.assessment_ready(unit,up):raise HTTPException(409,'Use Meta hints or explanations on the current task first. Optional Hub practice is available after passing this lesson.')
        if signals['quiet']:raise HTTPException(409,'Lesson Hub stays quiet during an independent check.')
        if automatic and not state['auto_hub']:raise HTTPException(409,'Automatic concept follow-up is paused.')
        previous=state['extras'].get(concept)
        if previous and not (retry and not automatic and previous['status'] in {'failed','cancelled'} and previous.get('attempts',1)<2):return self.extra_public(who,concept,previous)
        if not self.meta.enabled or self.store.provider_allowance().get('remaining_requests',0)<5:raise HTTPException(409,'This follow-up needs Meta and room for five requests including separate claim reviews within the existing allowance.')
        if len(self.tasks)>=6:raise HTTPException(429,'Wait for the current processing jobs to finish.')
        entry={'id':uuid.uuid4().hex,'status':'queued','parent_id':record['lesson_id'],'message':'Preparing one focused follow-up. Your course lesson stays saved.','created':time.time(),'automatic':automatic,'reason':reason,'attempts':previous.get('attempts',1)+1 if previous else 1}
        self.change(who,lambda s:s['extras'].update({concept:entry}))
        async def prepare():
            try:
                self.change(who,lambda s:s['extras'][concept].update(status='running'))
                unit=record['curriculum']['units'][0]
                context={'explanation':unit['explanation'][:1600],'main_task':unit['exercise']['instructions'][:1200],'source_ids':[d['id'] for d in record.get('source_documents',[])]}
                identifier=uuid.uuid4().hex;artifact=await self.agent.prepare(who,concept,identifier,extra=True,signals={k:v for k,v in signals.items() if k in {'wrong_questions','failed_practice_runs','concept'}}|{'requested_help':reason},base_context=context)
                extra=self.record(artifact,identifier,'extra',parent_id=record['lesson_id']);self.store.save_lesson(who,extra)
                self.change(who,lambda s:s['extras'][concept].update(status='ready',lesson_id=identifier,message='A focused explanation, topic check and practice are ready. Open it when you choose; your base lesson is unchanged.'))
            except asyncio.CancelledError:
                self.change(who,lambda s:s['extras'][concept].update(status='cancelled',message='Follow-up paused. Your course lesson is saved.'));raise
            except Exception as error:
                message=str(error)[:350] if isinstance(error,(ValueError,MetaUnavailable)) else 'The follow-up could not be prepared.'
                self.change(who,lambda s:s['extras'][concept].update(status='failed',message=message+' Your course lesson is saved.'))
            finally:self.tasks.pop('course:'+who+':'+entry['id'],None)
        self.tasks['course:'+who+':'+entry['id']]=asyncio.create_task(prepare())
        return entry


def install_course_routes(app,owner,service):
    @app.get('/api/course')
    async def catalog(request:Request):return service.catalog(owner(request))

    @app.get('/api/course/session')
    async def session(request:Request):
        who=owner(request);service.state(who);record=service.store.progress(who).get('course_session')
        if record and record.get('course_version')==VERSION:
            record=service.teaching_record(who,record);service.store.set_progress(who,'course_session',record)
        if record and record.get('course_version')!=VERSION and not record.get('course_legacy') and service.base(record['course_concept']):
            try:return {'session':await service.open(who,record['course_concept'])}
            except HTTPException as error:
                if error.status_code!=409:raise
        return {'session':public_session(record)}

    @app.post('/api/course/earlier/open')
    async def earlier(body:OpenEarlier,request:Request):
        who=owner(request,True)
        if body.lesson_id not in service.state(who).get('legacy_lessons',{}).values():raise HTTPException(404,'That earlier attempt is not part of this browser course history.')
        record=service.store.saved_lesson(who,body.lesson_id)
        if not record:raise HTTPException(404,'That earlier attempt was not found.')
        record['course_legacy']=True;service.store.set_progress(who,'course_session',record)
        return {'session':public_session(record)}

    @app.post('/api/course/open')
    async def open_topic(body:OpenTopic,request:Request):
        who=owner(request,True);return {'session':await service.open(who,body.concept_id)}

    @app.post('/api/course/automatic-hub')
    async def permission(body:Permission,request:Request):
        who=owner(request,True)
        if body.enabled and not body.consent:raise HTTPException(409,'Allow aggregate check results and public sources to be processed by Meta before enabling automatic follow-ups.')
        def change(state):
            if state['revision']!=body.revision:raise HTTPException(409,'Course settings changed in another tab. Reload them before saving.')
            state['revision']+=1;state['auto_hub']=body.enabled
        service.change(who,change)
        if not body.enabled:
            for entry in service.state(who)['extras'].values():
                task=service.tasks.get('course:'+who+':'+entry['id'])
                if task:task.cancel()
        return service.catalog(who)

    @app.post('/api/course/extra')
    async def extra(body:ExtraInput,request:Request):
        who=owner(request,True)
        if not body.consent:raise HTTPException(409,'Allow Meta research before requesting this personal follow-up.')
        record=service.store.saved_lesson(who,body.lesson_id)
        if not record or record.get('course_concept')!=body.concept_id or record.get('course_version')!=VERSION:raise HTTPException(404,'This course lesson was not found for this learner.')
        progress=service.store.progress(who).get(key(record['lesson_id']))
        if not progress:raise HTTPException(409,'Open this course lesson first.')
        return service.begin_extra(who,record,service.signals(record,progress),reason=body.reason,retry=body.retry)

    @app.post('/api/course/extra/open')
    async def open_extra(body:OpenTopic,request:Request):
        who=owner(request,True);entry=service.state(who)['extras'].get(body.concept_id)
        if not entry or entry['status']!='ready':raise HTTPException(409,'That concept follow-up is not ready yet.')
        record=service.store.saved_lesson(who,entry['lesson_id'])
        if not record:raise HTTPException(404,'This follow-up was not found for this learner.')
        service.access(who,record,record['curriculum']['units'][0]);service.store.set_progress(who,'course_session',record)
        service.change(who,lambda s:s['extras'][body.concept_id].update(opened=True))
        return {'session':public_session(record)}
