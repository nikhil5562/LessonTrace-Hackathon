"""Meta-authored video lessons with reference code checked by actual CPython."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any,Literal

from pydantic import BaseModel,ConfigDict,Field
from .guest import validate
from .teaching_quality import QUALITY_INSTRUCTION,check_note_walkthrough,check_control_premise
from . import grounding


class Spec(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Prediction(Spec):
    prompt: str=Field(min_length=8,max_length=500)
    code: str=Field(min_length=10,max_length=2500)
    options: list[str]=Field(min_length=3,max_length=4)
    expected_output: str=Field(max_length=1200)
    explanation: str=Field(min_length=10,max_length=1000)
    sources: list[str]=Field(min_length=1,max_length=6)


class QuizQuestion(Spec):
    kind: Literal['concept','complete_code']
    prompt: str=Field(min_length=8,max_length=400)
    code: str=Field(max_length=1200)
    options: list[str]=Field(min_length=3,max_length=4)
    answer_index: int=Field(ge=0,le=3)
    expected_output: str=Field(max_length=800)
    explanation: str=Field(min_length=10,max_length=700)
    sources: list[str]=Field(min_length=1,max_length=6)


class QuizBatch(Spec):
    quiz: list[QuizQuestion]=Field(min_length=1,max_length=6)


class Case(Spec):
    arguments: list[Any]=Field(max_length=4)
    expected: Any


class Exercise(Spec):
    kind: Literal['function','program']='function'
    parameters: list[str]=Field(default_factory=list,max_length=4)
    title: str=Field(min_length=5,max_length=120)
    instructions: str=Field(min_length=20,max_length=1200)
    entry: str=Field(pattern=r'^[a-z][a-z0-9_]{0,40}$')
    starter: str=Field(min_length=10,max_length=3000)
    reference_solution: str=Field(min_length=10,max_length=4000)
    preserve_input: bool
    cases: list[Case]=Field(min_length=3,max_length=4)
    sources: list[str]=Field(min_length=1,max_length=6)


class Unit(Spec):
    id: str=Field(pattern=r'^[a-z][a-z0-9-]{0,35}$')
    title: str=Field(min_length=5,max_length=100)
    explanation: str=Field(min_length=40,max_length=1600)
    opening_question: str=Field(min_length=8,max_length=350)
    sources: list[str]=Field(min_length=1,max_length=6)
    quiz: list[QuizQuestion]=Field(min_length=1,max_length=2)
    prediction: Prediction
    exercise: Exercise


class Lesson(Spec):
    title: str=Field(min_length=5,max_length=120)
    answer: str=Field(min_length=200,max_length=6000)
    sources: list[str]=Field(min_length=1,max_length=12)
    units: list[Unit]=Field(min_length=1,max_length=3)


INSTRUCTION='''Build an original, beginner-friendly interactive Python lesson from these video captions. Confirmed learner_preferences can guide presentation, never objectives, correctness or evidence of learning.
The captions are the only video evidence. Do not claim to inspect frames or transcribe audio yourself.
Return the requested structured JSON. Every teaching explanation, prediction and exercise must be authored by you for concepts actually present in these captions, not a generic unrelated course.
Write 350-500 words of readable Markdown study notes in answer: short ## headings, paragraphs, fenced python examples, common mistakes and self-checks. Cite the supplied caption IDs beside supported explanations. Label your new examples as added practice.
Create three short units when the source supports three concepts, otherwise one or two. Order them from a simple mental model to a fresh application. Each explanation should teach one concept in 60-100 words with Markdown. Each opening_question must be a short unanswered question for the learner; do not include its answer.
Each prediction must show a complete standalone program, at most 12 lines, printing a small result. Its options must be three or four exact possible printed outputs, with one matching expected_output. Preserve newlines in output strings. An intentional error may use its exact exception type such as KeyError as expected_output and one option. The explanation describes the actual program logic, not imaginary execution.
Before that output prediction, include ONE brief quiz question per unit about that unit's explanation. Use kind concept for a mental-model question, or complete_code for a tiny program with exactly one ___ placeholder and three or four single-line code fragments. Put a concrete Python premise in the code field, never an assignment or collection literal embedded in the prose prompt. For concept, code may be empty when no concrete premise is needed; otherwise supply a complete runnable setup of at most 12 lines, with expected_output empty. Quote string literals with single or double quotes, including strings inside lists and dictionaries. Bare names are variables and must be defined before use; do not silently treat names as text. Concept context must execute without errors; questions about intentional errors belong in output predictions. For complete_code, exactly one option must produce expected_output when substituted; Python will verify it. Supply answer_index and a short explanation for feedback after answering. Keep the question distinct from the function exercise and do not reveal that exercise's solution. These optional formative checks do not award mastery.
Each exercise is a distinct small function task related to that unit. Supply a short clear contract, a starter containing pass or one repairable logic mistake, a correct reference_solution and three varied argument/expected-return cases. Cases call entry(*arguments). A function must return its answer, not only print. Include an empty/boundary or changed-value case when appropriate. The starter must fail at least one case; never put the complete solution in starter or notes. Say in the instructions whether input changes are allowed, matching preserve_input.
Supported Python only: ordinary positional functions with optional scalar literal defaults; assignments; int, float, bool, None and short strings; lists, tuples and dictionaries; subscripts; arithmetic/comparisons; if; for/while; break/continue/for-else; return; print/len/range; list append/copy and dictionary get/keys/values/items/pop/popitem; f-strings. No imports, input(), comprehensions, slices, sets, classes, exceptions/try, private names, annotations, decorators or files/network. Do not use sum or unsupported helper functions. Keep examples small enough for 350 trace events and five seconds.
JSON values in cases must be ordinary finite numbers, strings, booleans, null, small lists or dictionaries with string keys only (including nested input dictionaries). Do not return tuples from an exercise. Use exactly the supplied source IDs in all sources lists. No score or explanation proves mastery.'''+'\n'+QUALITY_INSTRUCTION


def digest(source):return hashlib.sha256(source.encode()).hexdigest()


def source_schema(model,source_ids):
    """Constrain every citation array to passages actually in this request."""
    schema=model.model_json_schema()
    def restrict(value):
        if isinstance(value,dict):
            for name,field in value.get('properties',{}).items():
                if name in {'sources','evidence_ids'}:field['items']={'type':'string','enum':list(source_ids)}
            for child in value.values():restrict(child)
        elif isinstance(value,list):
            for child in value:restrict(child)
    restrict(schema)
    return grounding.schema(schema,source_ids)


def bounded(value,depth=0):
    if depth>6:raise ValueError('An exercise value is too deeply nested.')
    if value is None or isinstance(value,bool):return
    if isinstance(value,(int,float)):
        if not math.isfinite(value) or abs(value)>1_000_000:raise ValueError('Use finite, small exercise numbers.')
    elif isinstance(value,str):
        if len(value)>300:raise ValueError('An exercise string is too long.')
    elif isinstance(value,(list,dict)):
        if len(value)>30:raise ValueError('An exercise collection is too large.')
        if isinstance(value,dict):
            for key,item in value.items():bounded(key,depth+1);bounded(item,depth+1)
        else:
            for item in value:bounded(item,depth+1)
    else:raise ValueError('Use JSON-compatible exercise values.')


def check_sources(value,allowed):
    if isinstance(value,dict):
        if 'sources' in value and (not value['sources'] or any(s not in allowed for s in value['sources'])):
            raise ValueError('A generated explanation used an unknown caption source.')
        for item in value.values():check_sources(item,allowed)
    elif isinstance(value,list):
        for item in value:check_sources(item,allowed)
    elif isinstance(value,str):
        if any(s not in allowed for s in re.findall(r'\[((?:video|hub)-[A-Za-z0-9_-]+)\]',value)):
            raise ValueError('A generated explanation used an unknown inline caption source.')


def exercise_payload(exercise,source,arguments,trace_case=0):
    if exercise.get('kind','function')=='program':
        return {'source':source,'entry':None,'arguments':arguments,'trace_case':trace_case,'program_inputs':exercise['parameters'],'result_name':exercise['entry']}
    return {'source':source,'entry':exercise['entry'],'arguments':arguments,'trace_case':trace_case}


async def checked_run(execution,source,entry,arguments,exercise=None):
    validate(source,entry)
    if len(source.splitlines())>60:raise ValueError('A generated example is too long.')
    raw=await execution.execute(exercise_payload(exercise,source,arguments) if exercise is not None else {'source':source,'entry':entry,'arguments':arguments,'trace_case':0})
    if raw.get('error'):raise ValueError('Python could not check this program: '+json.dumps(raw['error'])[:350])
    if raw.get('source_sha256')!=digest(source):raise ValueError('Python source verification failed.')
    if len(raw.get('cases',[]))!=len(arguments):raise ValueError('Python did not return every requested case.')
    return raw


def case_passed(case,expected,arguments,preserve):
    return not case.get('error') and case.get('return_type')==type(expected).__name__ and case.get('actual')==expected and (not preserve or case.get('arguments_after')==arguments)


async def validate_lesson(result,execution,source_ids,chunks=None,lesson_model=Lesson):
    spec=lesson_model.model_validate({k:result[k] for k in lesson_model.model_fields}).model_dump()
    check_sources(spec,set(source_ids))
    if chunks is not None:spec['evidence_quotes']=grounding.verify(result,chunks,grounding.cited_ids(spec))
    if result.get('claim_review'):spec['claim_review']=result['claim_review']
    check_note_walkthrough(spec['answer'])
    if len({u['id'] for u in spec['units']})!=len(spec['units']):raise ValueError('Concept identifiers must be distinct.')
    for index,unit in enumerate(spec['units'],1):
        check_note_walkthrough(unit['explanation'])
        unit['quiz']=await validate_quiz(unit['quiz'],execution,source_ids)
        prediction=unit['prediction']
        if len(set(prediction['options']))!=len(prediction['options']) or any(len(o)>1200 for o in prediction['options']):raise ValueError('Use distinct, short prediction options.')
        raw=await checked_run(execution,prediction['code'],None,[[]])
        observed=raw['cases'][0]
        output=observed['error']['type'] if observed.get('error') else observed.get('output','').strip()
        options=[o.replace('\r\n','\n').strip() for o in prediction['options']]
        if prediction['expected_output'].strip()!=output or options.count(output)!=1:
            raise ValueError(f'Prediction {index} disagrees with actual Python output {output[:200]!r}. Correct its options and expected_output.')
        prediction['answer_index']=options.index(output)
        prediction['verification']={'source_hash':digest(prediction['code']),'runtime':raw['runtime'],'steps':len(observed.get('events',[])),'output':output}
        unit['exercise']=await validate_exercise(unit['exercise'],execution,source_ids)
    return spec


async def validate_quiz(questions,execution,source_ids):
    result=QuizBatch.model_validate({'quiz':questions}).model_dump()['quiz']
    check_sources(result,set(source_ids))
    for question_index,question in enumerate(result,1):
        prose=re.sub(r'\[(?:video|hub)-[A-Za-z0-9_-]+\]','',question['prompt'])
        if re.search(r'\b[A-Za-z_]\w*\s*=(?!=)',prose) or re.search(r'(?<![\w\]\)])[\[{]',prose) or '```' in prose:
            raise ValueError('Put the quiz example in the code field, not an assignment or collection literal inside the prose prompt. Quote string literals and include any variable definitions.')
        options=question['options']
        if len(set(o.strip() for o in options))!=len(options) or any(not o.strip() or len(o)>180 for o in options):
            raise ValueError('Quiz options must be short, nonempty and distinct.')
        if question['answer_index']>=len(options):raise ValueError('Choose an existing quiz answer.')
        if question['kind']=='concept':
            if question['expected_output']:raise ValueError('Concept checks must use an empty expected_output field.')
            if question['code'].strip():
                if len(question['code'].splitlines())>12:raise ValueError('Keep concept context under 12 lines.')
                raw=await checked_run(execution,question['code'],None,[[]])
                observed=raw['cases'][0]
                if observed.get('error'):
                    raise ValueError('The concept example raises '+observed['error']['type']+'. Quote string literals and define variables before using them. Use an output prediction for intentional errors.')
                premise=check_control_premise(question,question['code'],observed)
                question['verification']={'basis':'Concept context executed with actual CPython; conceptual answer remains Meta-authored','source_hash':digest(question['code']),'runtime':raw['runtime']}
                if premise:question['verification']['control_premise']=premise
            else:
                check_control_premise(question,'',{})
                question['verification']={'basis':'Meta-authored concept check; no executable context supplied'}
            continue
        if question['code'].count('___')!=1 or len(question['code'].splitlines())>12 or not question['expected_output'].strip():
            raise ValueError('Code-completion checks need one ___ placeholder and a short printed result.')
        matches=[];observations={}
        for index,option in enumerate(options):
            if '\n' in option or '\r' in option:raise ValueError('Use single-line code fragments in quiz choices.')
            try:
                raw=await checked_run(execution,question['code'].replace('___',option),None,[[]])
            except (ValueError,SyntaxError):continue
            observed=raw['cases'][0]
            observations[index]=observed
            if not observed.get('error') and observed.get('output','').strip()==question['expected_output'].strip():matches.append(index)
        if matches!=[question['answer_index']]:raise ValueError(f'Question {question_index}: exactly one answer must match. Completion options {matches} match the output, but only answer_index {question["answer_index"]} must match. Change ambiguous distractors or correct the expected output.')
        premise=check_control_premise(question,question['code'].replace('___',options[matches[0]]),observations[matches[0]])
        question['verification']={'basis':'Choices checked with actual CPython','source_hash':digest(question['code'])}
        if premise:question['verification']['control_premise']=premise
    return result


async def validate_exercise(result,execution,source_ids):
    exercise=Exercise.model_validate({k:result[k] for k in Exercise.model_fields if k in result}).model_dump()
    check_sources(exercise,set(source_ids))
    if exercise['kind']=='program':
        names=exercise['parameters']+[exercise['entry']]
        if len(set(names))!=len(names) or any(not re.fullmatch(r'[a-z][a-z0-9_]{0,40}',n) or n in {'print','len','range','sum'} for n in names):raise ValueError('Use distinct ordinary input and result names for program practice.')
        if any(len(c['arguments'])!=len(exercise['parameters']) for c in exercise['cases']):raise ValueError('Each program check must supply its named inputs.')
    elif exercise['parameters']:raise ValueError('Function exercise parameters belong in its definition, not program input names.')
    for case in exercise['cases']:bounded(case['arguments']);bounded(case['expected'])
    if len({json.dumps(c['arguments'],sort_keys=True) for c in exercise['cases']})<3:
        raise ValueError('Use at least three distinct exercise inputs.')
    args=[c['arguments'] for c in exercise['cases']]
    entry=None if exercise['kind']=='program' else exercise['entry']
    raw=await checked_run(execution,exercise['reference_solution'],entry,args,exercise)
    if not all(case_passed(c,spec_case['expected'],args[i],exercise['preserve_input']) for i,(c,spec_case) in enumerate(zip(raw['cases'],exercise['cases']))):
        raise ValueError('The reference solution disagrees with its expected returns or input-preservation contract.')
    starter=await checked_run(execution,exercise['starter'],entry,args,exercise)
    if all(case_passed(c,spec_case['expected'],args[i],exercise['preserve_input']) for i,(c,spec_case) in enumerate(zip(starter['cases'],exercise['cases']))):
        raise ValueError('The starter already passes every case. Supply an unfinished starter.')
    exercise['verification']={'source_hash':digest(exercise['reference_solution']),'runtime':raw['runtime'],'cases':len(args)}
    if result.get('claim_review'):exercise['claim_review']=result['claim_review']
    return exercise
