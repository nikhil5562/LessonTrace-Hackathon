"""Owned learning continuity, confirmed preferences and one opt-in research follow-up."""
from __future__ import annotations

import ast
import json
import re
import time
import uuid
from typing import Literal

from fastapi import HTTPException,Request
from pydantic import Field

from . import adaptive,video_quiz
from .video_curriculum import Spec,digest
from .video_lessons import public_session


def defaults():
    return {'preferences':{'revision':0,'goal':'','explanation':'balanced','representation':'references','hints':'question_first','suggestions':True},'research':{},'events':[]}


class Preferences(Spec):
    revision:int=Field(ge=0)
    goal:str=Field(default='',max_length=350)
    explanation:Literal['balanced','short_steps','detailed']='balanced'
    representation:Literal['references','boxes','frames']='references'
    hints:Literal['question_first','small_hint']='question_first'
    suggestions:bool=True


class Reset(Spec):
    revision:int=Field(ge=0)


class LessonScope(Spec):
    lesson_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    unit_id:str=Field(max_length=36)


class ResearchPermission(LessonScope):
    enabled:bool=False
    consent:bool=False


class ResearchOnce(LessonScope):
    consent:bool=False


class Resume(Spec):
    lesson_id:str=Field(pattern=r'^[a-f0-9]{32}$')


def lesson_progress(record,data):
    from .video_learning import blank_progress,progress_key
    progress=data.get(progress_key(record['lesson_id'])) or blank_progress(record)
    adaptive.upgrade(progress,record['curriculum']['units'])
    unit=record['curriculum']['units'][progress['current_unit']]
    up=adaptive.unit_state(progress,unit['id']);activity=adaptive.active(up)
    return progress,unit,up,activity


def summary(record,data):
    progress,unit,up,activity=lesson_progress(record,data)
    stage='complete' if progress['complete'] else 'quiz' if up['phase']=='prediction' else {'practice':'practice','simpler':'smaller_practice','fresh':'fresh_check','review':'later_review'}[activity['kind']]
    if stage=='practice' and up['practice_passed']:stage='ready_for_fresh'
    quiz=video_quiz.status(unit,up)
    lesson_first=record.get('course_flow')=='lesson-first'
    checked=bool(lesson_first and up.get('lesson_opened') and up['practice_passed'] and video_quiz.assessment_ready(unit,up))
    if lesson_first:stage='complete' if checked else 'lesson' if up['phase']=='lesson' else 'quiz' if up['phase']=='prediction' else 'practice'
    return {'lesson_id':record['lesson_id'],'context':record.get('context','video'),'title':record['title'],'unit_id':unit['id'],'unit_title':unit['title'],
        'stage':stage,'activity_kind':activity['kind'],'attempts':activity['attempts'],'failures':activity['failures'],'practice_passed':up['practice_passed'],
        'independent_passed':up['independent_passed'],'review_due_at':up['review_due_at'],'quiz_answered':quiz['answered'],'quiz_total':len(quiz['items']),
        'quiz_skipped':quiz['skipped'],'supported':activity['supported'],'complete':progress['complete'] or checked,
        'quiet':activity['kind'] in {'fresh','review'} and not activity['independent_run_id'],
        'expectation_recorded':bool(activity['learner_expectation']),'last_run_id':up['last_run_id']}


def loops_supported(unit):
    if not re.search(r'\b(loop|loops|iteration|iterate|iterating|break|continue|range)\b',unit['title']+' '+unit['explanation'],re.I):return False
    try:
        return any(isinstance(node,(ast.For,ast.While)) for source in [unit['prediction']['code'],unit['exercise']['reference_solution']] for node in ast.walk(ast.parse(source)))
    except SyntaxError:return False


class LearningCoach:
    def __init__(self,store,meta,tasks):
        self.store,self.meta,self.tasks=store,meta,tasks;self.hub=None

    def state(self,who):return self.store.progress(who).get('coach_state') or defaults()

    def mutate(self,who,change):return self.store.mutate_progress(who,'coach_state',defaults(),change)

    def remember(self,who,record):
        if record and record.get('curriculum') and re.fullmatch(r'[a-f0-9]{32}',record.get('lesson_id','')):self.store.save_lesson(who,record)

    def sync(self,who):
        data=self.store.progress(who)
        for key in ('youtube_session','hub_session','course_session'):
            record=data.get(key)
            if record and record.get('curriculum') and not self.store.saved_lesson(who,record['lesson_id']):self.remember(who,record)
        return data

    def preferences(self,who):return self.state(who)['preferences']

    def teaching_preferences(self,who):
        p=self.preferences(who)
        return {k:p[k] for k in ('goal','explanation','representation','hints')} if p['revision'] else {}

    def current(self,who,identifier,unit_id=None):
        data=self.sync(who)
        record=next((data.get(k) for k in ('youtube_session','hub_session','course_session') if data.get(k,{}).get('lesson_id')==identifier),None)
        if not record or not record.get('curriculum'):raise HTTPException(409,'Reopen this saved lesson before changing its coach settings.')
        progress,unit,up,activity=lesson_progress(record,data)
        if unit_id and unit['id']!=unit_id:raise HTTPException(409,'The concept changed. Reopen the coach before continuing.')
        return record,progress,unit,up,activity

    def observe(self,who,record,progress,event='progress'):
        self.remember(who,record)
        data={**self.store.progress(who),'video_progress_'+record['lesson_id']:progress};snapshot=summary(record,data)
        marker=digest(json.dumps(snapshot,sort_keys=True))
        def add(state):
            if any(item['id']==marker for item in state['events']):return
            state['events']=(state['events']+[{'id':marker,'event':event,'lesson_id':record['lesson_id'],'unit_id':snapshot['unit_id'],'stage':snapshot['stage'],
                'attempts':snapshot['attempts'],'failures':snapshot['failures'],'quiz_skipped':snapshot['quiz_skipped'],'supported':snapshot['supported'],'at':time.time()}])[-80:]
        self.mutate(who,add)
        try:
            _,unit,up,activity=lesson_progress(record,data)
            grant=self.state(who)['research'].get(record['lesson_id'],{})
            if record.get('context')!='course' and self.preferences(who)['suggestions'] and grant.get('enabled') and grant.get('unit_id')==unit['id'] and not grant.get('used') and activity['kind']=='practice' and up['phase']=='exercise' and activity['failures']>=2 and activity['learner_expectation'] and not activity['passed']:
                self.research(who,record['lesson_id'],unit['id'],automatic=True)
        except HTTPException as error:
            def failed(state):
                grant=state['research'].get(record['lesson_id'])
                if grant:grant['last_error']=str(error.detail)[:250]
            self.mutate(who,failed)

    def stop_jobs(self,who,identifiers):
        if not self.hub:return
        for identifier in identifiers:
            if not identifier:continue
            try:self.hub['stop'](who,identifier)
            except HTTPException as error:
                if error.status_code!=404:raise

    def save_preferences(self,who,body,reset=False):
        stopping=[]
        def change(state):
            old=state['preferences']
            if body.revision!=old['revision']:raise HTTPException(409,'Preferences changed in another tab. Reload them before saving.')
            new=defaults()['preferences'] if reset else body.model_dump()
            new['goal']=new['goal'].strip();new['revision']=old['revision']+1
            if reset or new['goal']!=old['goal'] or not new['suggestions']:
                for grant in state['research'].values():
                    stopping.append(grant.get('job_id'))
                    grant['enabled']=False;grant.pop('goal',None)
            state['preferences']=new
        state=self.mutate(who,change);self.stop_jobs(who,stopping)
        return state['preferences']

    def allow_research(self,who,body):
        record,_,unit,_,activity=self.current(who,body.lesson_id,body.unit_id)
        if body.enabled:
            if not body.consent:raise HTTPException(409,'Allow the stated goal, concept and attempt summary to be sent to Meta before enabling research.')
            if activity['kind'] in {'fresh','review'}:raise HTTPException(409,'Automatic research stays paused during a fresh check. Ask the tutor if you need help.')
            if not loops_supported(unit):raise HTTPException(409,'The current research pilot supports Python loops. Your existing lesson still works.')
            if not self.meta.enabled or not self.hub:raise HTTPException(409,'Meta research is unavailable in this server.')
            if not self.preferences(who)['suggestions']:raise HTTPException(409,'Enable next-step suggestions before enabling automatic research.')
        previous=self.state(who)['research'].get(body.lesson_id,{})
        def change(state):
            grant=state['research'].setdefault(body.lesson_id,{'used':False})
            grant.update(enabled=body.enabled,goal=state['preferences']['goal'],granted_at=time.time(),unit_id=unit['id'])
        self.mutate(who,change)
        if not body.enabled:self.stop_jobs(who,[previous.get('job_id')])
        if body.enabled:
            progress=self.store.progress(who).get('video_progress_'+body.lesson_id)
            if progress:self.observe(who,record,progress,'research_permission')

    def can_research(self,who,record,unit,up,chat=False):
        if record.get('context')=='course':return False
        grant=self.state(who)['research'].get(record['lesson_id'],{})
        return bool(self.hub and self.meta.enabled and grant.get('enabled') and grant.get('unit_id')==unit['id'] and not grant.get('used') and up['phase']=='exercise' and adaptive.active(up)['kind']=='practice'
            and loops_supported(unit) and self.store.provider_allowance().get('remaining_requests',0)>=(8 if chat else 6))

    def research(self,who,identifier,unit_id,consent=False,automatic=False):
        from .hub import HubInput
        record,_,unit,up,activity=self.current(who,identifier,unit_id)
        if record.get('context')=='course':raise HTTPException(409,'Use the prerequisite-checked concept follow-up inside this course.')
        if activity['kind'] in {'fresh','review'}:raise HTTPException(409,'Research stays out of fresh checks. Ask the tutor if you want supported practice.')
        if not loops_supported(unit):raise HTTPException(409,'The research pilot currently supports loop concepts only.')
        if not self.hub or not self.meta.enabled:raise HTTPException(409,'Meta research is unavailable in this server.')
        state=self.state(who);grant=state['research'].get(identifier,{})
        if automatic and (not grant.get('enabled') or grant.get('unit_id')!=unit_id):raise HTTPException(409,'Automatic research is not enabled for this concept.')
        if not automatic and not consent:raise HTTPException(409,'Allow the stated research context to be sent to Meta first.')
        if grant.get('used'):
            if grant.get('job_id'):return self.hub['payload'](who,self.hub['saved'](who,grant['job_id']))
            raise HTTPException(409,'This follow-up is already being prepared.')
        if self.store.provider_allowance().get('remaining_requests',0)<6:raise HTTPException(409,'This follow-up needs room for six model requests including separate claim reviews in the approved allowance.')
        job_id=uuid.uuid4().hex;goal=grant.get('goal','') if automatic else state['preferences']['goal']
        expectation=activity['learner_expectation'][:180]
        question=('Help me practise '+unit['title']+'. '+goal+(' Learner stated: '+expectation if expectation else '')+' Prepare one focused explanation and checked practice for this loop concept.')[:700]
        focus='nested-break' if re.search(r'\b(nested|inner|outer|break)\b',unit['title']+' '+unit['explanation'],re.I) else 'range-iteration' if re.search(r'\brange\b',unit['title'],re.I) else 'foundations'
        def claim(state):
            current=state['research'].setdefault(identifier,{'enabled':False,'used':False})
            if current.get('used'):raise HTTPException(409,'A follow-up is already preparing for this lesson. Refresh the coach.')
            if automatic and (not current.get('enabled') or current.get('unit_id')!=unit_id):raise HTTPException(409,'Automatic research was paused.')
            current.update(used=True,job_id=job_id,unit_id=unit_id,unit_title=unit['title'],started=time.time(),automatic=automatic,last_error='')
        self.mutate(who,claim)
        context={'title':unit['title'],'explanation':unit['explanation'][:500],
            'attempt_summary':{'attempts':activity['attempts'],'failures':activity['failures'],'learner_expectation':expectation}}
        try:return self.hub['begin'](who,HubInput(goal=question,focus=focus,consent=True,request_id=job_id),publish=False,base_context_override=context)
        except HTTPException:
            def release(state):
                current=state['research'][identifier]
                if current.get('job_id')==job_id:current.update(used=False,job_id='')
            self.mutate(who,release);raise

    def research_state(self,who,identifier):
        grant=self.state(who)['research'].get(identifier,{})
        result={k:v for k,v in grant.items() if k in {'enabled','used','unit_id','unit_title','last_error','automatic','opened'}}
        if grant.get('job_id') and self.hub:
            try:
                payload=self.hub['payload'](who,self.hub['saved'](who,grant['job_id']))
                result['job']=payload['job'];result['lesson_id']=payload['session']['lesson_id'] if payload.get('session') else None
            except HTTPException as error:
                if error.status_code!=404:raise
                result['last_error']='Research was interrupted before it started. Enable or request a follow-up again.'
                def release(state):
                    entry=state['research'][identifier];entry.update(used=False,enabled=False,job_id='')
                self.mutate(who,release)
        return result

    def dashboard(self,who,identifier=None):
        data=self.sync(who);prefs=self.preferences(who);lessons=[]
        for entry in self.store.lesson_list(who):
            record=self.store.saved_lesson(who,entry['id']);item=summary(record,data);item['updated']=entry['updated'];lessons.append(item)
        chosen=next((item for item in lessons if item['lesson_id']==identifier),None) if identifier else (lessons[0] if lessons else None)
        if identifier and not chosen:raise HTTPException(404,'This saved lesson was not found in this browser.')
        research=self.research_state(who,chosen['lesson_id']) if chosen else {}
        if chosen and research.get('unit_id')!=chosen['unit_id']:research['enabled']=False
        updates=[]
        for item in lessons:
            if chosen and item['lesson_id']==chosen['lesson_id']:continue
            extra=self.research_state(who,item['lesson_id']);job=extra.get('job',{})
            if job.get('status') in {'queued','running','ready'} and not extra.get('opened'):
                updates.append({'title':extra.get('unit_title',item['unit_title']),'base_lesson_id':item['lesson_id'],'lesson_id':extra.get('lesson_id'),'status':job['status'],'message':job['message']})
        card=None;eligible=False
        if chosen:
            record=self.store.saved_lesson(who,chosen['lesson_id']);progress,unit,up,activity=lesson_progress(record,data)
            eligible=record.get('context')!='course' and loops_supported(unit) and activity['kind'] not in {'fresh','review'}
            if prefs['suggestions']:
                if chosen['quiet']:
                    card={'kind':'quiet','title':'Your fresh check is yours to try','text':'Run and visualise your code. Ask Meta whenever you want help; that will be recorded as supported practice.','action':None,'basis':'saved_progress'}
                elif research.get('job',{}).get('status')=='ready' and not research.get('opened'):
                    card={'kind':'research_ready','title':'A focused follow-up is ready','text':'Meta prepared extra notes and checked practice for '+research.get('unit_title',chosen['unit_title'])+'. Your current lesson is saved.','action':'open_research','lesson_id':research['lesson_id'],'basis':'meta_research'}
                elif research.get('job',{}).get('status') in {'queued','running'}:
                    card={'kind':'researching','title':'Preparing one useful follow-up','text':research['job']['message'],'action':'stop_research','basis':'meta_research'}
                elif research.get('job',{}).get('status') in {'failed','cancelled'}:
                    card={'kind':'research_stopped','title':'Your current work is still saved','text':research['job']['message'],'action':'research_details','basis':'research_status'}
                elif up['review_due_at'] and up['review_due_at']<=time.time() and up['independent_passed']:
                    card={'kind':'review_due','title':'A later review is due','text':'Try a new task for this concept before asking for hints.','action':'review','unit_id':unit['id'],'basis':'saved_progress'}
                elif chosen['complete']:
                    card={'kind':'complete','title':'This session’s checks are complete','text':'Open the next teaching lesson from the course. Additional practice is optional.' if record.get('course_flow')=='lesson-first' else 'A later fresh task checks whether you can apply the idea again. This is not a mastery score.','action':None,'basis':'saved_progress'}
                elif adaptive.next_step(progress,up,quiz_ready=video_quiz.ready(unit,up))[0]:
                    action,label=adaptive.next_step(progress,up,quiz_ready=video_quiz.ready(unit,up))
                    card={'kind':'next_activity','title':label.replace(' →',''),'text':'Your saved checks make this next activity available. Your draft stays with its lesson.','action':action,'basis':'saved_progress'}
                elif activity['failures']>=2 and not activity['learner_expectation']:
                    card={'kind':'expectation','title':'What did you expect to happen?','text':'Describe the result you expected and why. A failing run alone does not tell us what confused you.','action':'explain_expectation','basis':'saved_progress'}
                elif activity['failures']>=2 and eligible and not research.get('used'):
                    card={'kind':'research_offer','title':'Another explanation may help','text':'You can prepare one focused Loops follow-up from the official reference and curated sources.','action':'research_settings','basis':'saved_progress'}
                else:
                    card={'kind':'current_activity','title':'Read, then try a quick check' if up['phase']=='prediction' else 'Try the idea in your own code',
                        'text':'The quiz is optional. Skip to coding whenever you are ready.' if up['phase']=='prediction' else 'Use the editor and actual execution to check your thinking. Ask Meta when a specific step is unclear.',
                        'action':None,'basis':'saved_progress'}
        return {'preferences':prefs,'lessons':lessons,'current':chosen,'next_step':card,'research':research,'updates':updates,'research_supported':eligible,
            'usage':self.store.provider_usage(who,chosen['lesson_id']) if chosen else self.store.provider_usage(who),
            'events':[event for event in self.state(who)['events'] if not chosen or event['lesson_id']==chosen['lesson_id']][-8:],
            'allowance':self.store.provider_allowance(),'meta_enabled':self.meta.enabled,'scope':'Local browser memory and updates while this backend runs. Voice calls and cloud notifications are not part of this version.'}


def install_coach_routes(app,owner,store,coach):
    @app.get('/api/coach')
    async def state(request:Request,lesson_id:str|None=None):return coach.dashboard(owner(request),lesson_id)

    @app.post('/api/coach/preferences')
    async def preferences(body:Preferences,request:Request):
        return {'preferences':coach.save_preferences(owner(request,True),body)}

    @app.post('/api/coach/preferences/reset')
    async def reset(body:Reset,request:Request):
        return {'preferences':coach.save_preferences(owner(request,True),body,reset=True)}

    @app.post('/api/coach/research-permission')
    async def permission(body:ResearchPermission,request:Request):
        who=owner(request,True);coach.allow_research(who,body);return coach.dashboard(who,body.lesson_id)

    @app.post('/api/coach/research')
    async def research(body:ResearchOnce,request:Request):
        who=owner(request,True);coach.research(who,body.lesson_id,body.unit_id,body.consent);return coach.dashboard(who,body.lesson_id)

    @app.post('/api/coach/resume')
    async def resume(body:Resume,request:Request):
        who=owner(request,True);coach.sync(who);record=store.saved_lesson(who,body.lesson_id)
        if not record:raise HTTPException(404,'This saved lesson was not found in this browser.')
        key={'hub':'hub_session','course':'course_session'}.get(record.get('context'),'youtube_session')
        previous=store.progress(who).get(key);coach.remember(who,previous);store.set_progress(who,key,record);coach.remember(who,record)
        def mark_opened(state):
            for grant in state['research'].values():
                if not grant.get('job_id'):continue
                job=store.progress(who).get('hub_job_'+grant['job_id'],{})
                if job.get('lesson_id')==body.lesson_id:grant['opened']=True
        coach.mutate(who,mark_opened)
        return {'session':public_session(record)}
