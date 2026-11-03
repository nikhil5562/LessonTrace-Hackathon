"""Checked corrections to saved teaching, preserving task contracts and attempts."""
from __future__ import annotations

import copy
import json
import time

from pydantic import Field

from .teaching_quality import check_note_walkthrough
from .video_curriculum import Spec,QuizQuestion,check_sources,validate_quiz
from . import grounding


class TeachingRevision(Spec):
    answer:str=Field(min_length=200,max_length=6000)
    explanation:str=Field(min_length=40,max_length=1600)
    quiz:list[QuizQuestion]=Field(min_length=1,max_length=2)


async def checked_revision(record,unit_id,result,execution):
    patch=TeachingRevision.model_validate({k:result[k] for k in TeachingRevision.model_fields}).model_dump()
    unit=next((unit for unit in record['curriculum']['units'] if unit['id']==unit_id),None)
    if not unit:raise ValueError('The concept to correct was not found.')
    allowed=[chunk['id'] for chunk in record['caption_chunks']]
    check_sources(patch,set(allowed));check_note_walkthrough(patch['answer']);check_note_walkthrough(patch['explanation'])
    patch['quiz']=await validate_quiz(patch['quiz'],execution,allowed)
    updated=copy.deepcopy(record)
    revised=next(unit for unit in updated['curriculum']['units'] if unit['id']==unit_id)
    updated['answer']=updated['curriculum']['answer']=patch['answer']
    revised['explanation']=patch['explanation'];revised['quiz']=patch['quiz']
    updated['teaching_revision']={'number':record.get('teaching_revision',{}).get('number',0)+1,'unit_id':unit_id,
        'model':result.get('model',record.get('model')),'at':time.time(),'scope':'Notes, concept explanation and optional quiz; code tasks and attempt records preserved.'}
    if 'evidence_quotes' in result:updated['teaching_revision']['evidence_quotes']=grounding.verify(result,record['caption_chunks'],grounding.cited_ids(patch))
    return updated


def publish_revision(store,owner,expected,updated):
    if updated['lesson_id']!=expected['lesson_id']:raise ValueError('A correction cannot replace the lesson identity.')
    identifier=expected['lesson_id']
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current=[row for row in db.execute("SELECT key,value FROM progress WHERE owner=? AND key IN ('youtube_session','hub_session')",(owner,)) if json.loads(row['value']).get('lesson_id')==identifier]
        archived=db.execute('SELECT record FROM learning_sessions WHERE owner=? AND id=?',(owner,identifier)).fetchone()
        copies=[json.loads(row['value']) for row in current]+([json.loads(archived['record'])] if archived else [])
        if not copies:raise ValueError('This saved lesson was not found for this browser.')
        if any(record!=expected for record in copies):raise ValueError('The saved lesson changed while its correction was being prepared. Existing work was kept.')
        serialized=json.dumps(updated)
        for row in current:db.execute('UPDATE progress SET value=? WHERE owner=? AND key=?',(serialized,owner,row['key']))
        db.execute('INSERT INTO learning_sessions VALUES (?,?,?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET title=excluded.title,record=excluded.record,updated=excluded.updated',
            (owner,identifier,updated.get('context','video'),updated['title'],serialized,time.time()))
    return {'current_copies':len(current),'archived':True}
