"""Optional formative checks; skipping never awards correctness or code evidence."""
from __future__ import annotations

import json
import time

from .video_curriculum import digest


def questions(unit):
    checks=[dict(question,id=f'lesson-check-{i+1}') for i,question in enumerate(unit.get('quiz',[]))]
    checks.append(dict(unit['prediction'],id='prediction',kind='prediction'))
    for question in checks:
        question['question_hash']=digest(json.dumps({k:question[k] for k in ('id','kind','prompt','code','options','sources','needs','targets','purpose') if k in question},sort_keys=True))
    return checks


def public_question(question):
    result={k:question[k] for k in ('id','kind','prompt','code','options','sources','question_hash','needs','targets','purpose') if k in question}
    if question['kind']=='complete_code':result['target_output']=question['expected_output'].strip()
    if question.get('purpose')=='debug' and question.get('bug_option_index') is not None:result['buggy_code']=question['code'].replace('___',question['options'][question['bug_option_index']]);result['bug_output']=question.get('bug_verification',{}).get('observed',question.get('expected_bug_output',''))
    return result


def status(unit,up):
    answers=up.get('quiz_answers',{})
    items=[]
    for question in questions(unit):
        saved=answers.get(question['id'])
        # Existing sessions already recorded their original output prediction.
        if not saved and question['id']=='prediction' and up['predictions']:
            saved=up['predictions'][-1]
        if saved and saved.get('question_hash',question['question_hash'])!=question['question_hash']:saved=None
        item={'id':question['id'],'attempted':bool(saved)}
        if saved:item.update(option=saved['option'],correct=saved['correct'],feedback=question['explanation'])
        items.append(item)
    return {'items':items,'answered':sum(item['attempted'] for item in items),'total':len(items),
            'complete':all(item['attempted'] for item in items),'skipped':up.get('quiz_skipped',False),
            'has_lesson_checks':bool(unit.get('quiz'))}


def ready(unit,up):
    quiz=status(unit,up)
    return quiz['complete'] or quiz['skipped']


def record_answer(up,question,option):
    correct=option==question['answer_index']
    saved={'option':option,'correct':correct,'at':time.time(),'question_hash':question['question_hash']}
    up.setdefault('quiz_answers',{})[question['id']]=saved
    up['quiz_history']=(up.get('quiz_history',[])+[saved|{'question_id':question['id'],'targets':question.get('targets',[]),'purpose':question.get('purpose','prediction' if question['id']=='prediction' else 'understanding')}])[-100:]
    if question['id']=='prediction':
        up['predictions']=(up['predictions']+[saved])[-30:]
        up['prediction_ok']=correct
    return correct


def assessment_ready(unit,up):
    status_now=status(unit,up)
    return bool(status_now['items']) and all(item.get('correct') for item in status_now['items'])
