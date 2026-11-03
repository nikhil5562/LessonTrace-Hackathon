"""A reusable base course is checked offline; learner extras use the same gates."""
import re
from typing import Literal
from pydantic import Field

from .video_curriculum import Lesson,Unit,Exercise,Prediction,QuizQuestion,checked_run,validate_lesson,validate_exercise
from . import course_policy as policy


class TaggedQuestion(QuizQuestion):
    needs:list[str]=Field(max_length=20)
    targets:list[str]=Field(min_length=1,max_length=1)
    purpose:Literal['understanding','practice','debug','common_mistake']
    bug_option_index:int|None=Field(default=None,ge=0,le=3)
    expected_bug_output:str=Field(default='',max_length=800)


class TaggedPrediction(Prediction):
    needs:list[str]=Field(max_length=20)
    targets:list[str]=Field(min_length=1,max_length=1)


class TaggedExercise(Exercise):
    needs:list[str]=Field(max_length=20)
    targets:list[str]=Field(min_length=1,max_length=1)
    required_helpers:list[str]=Field(default_factory=list,max_length=4)


class CourseUnit(Unit):
    quiz:list[TaggedQuestion]=Field(min_length=4,max_length=6)
    prediction:TaggedPrediction
    exercise:TaggedExercise
    fresh_exercise:TaggedExercise


class CourseLesson(Lesson):
    units:list[CourseUnit]=Field(min_length=1,max_length=1)


class ProgramTaggedExercise(TaggedExercise):
    kind:Literal['program']='program'


class CompactCourseUnit(CourseUnit):
    quiz:list[TaggedQuestion]=Field(min_length=4,max_length=4)
    exercise:TaggedExercise
    fresh_exercise:TaggedExercise


class CompactCourseLesson(CourseLesson):
    units:list[CompactCourseUnit]=Field(min_length=1,max_length=1)


class WideUnit(Unit):
    quiz:list[QuizQuestion]=Field(min_length=4,max_length=6)


class WideLesson(Lesson):
    units:list[WideUnit]=Field(min_length=1,max_length=1)


def authoring_view(curriculum):
    """Remove computed checks when revalidating an operator-reviewed draft."""
    result={k:curriculum[k] for k in Lesson.model_fields};result['evidence_quotes']=curriculum['evidence_quotes'];result['units']=[]
    for unit in curriculum['units']:
        clean={k:unit[k] for k in CourseUnit.model_fields}
        clean['quiz']=[{k:q[k] for k in TaggedQuestion.model_fields if k in q} for q in unit['quiz']]
        clean['prediction']={k:unit['prediction'][k] for k in TaggedPrediction.model_fields if k in unit['prediction']}
        for name in ('exercise','fresh_exercise'):clean[name]={k:unit[name][k] for k in TaggedExercise.model_fields if k in unit[name]}
        result['units'].append(clean)
    return result


async def check_course_lesson(result,execution,chunks,concept):
    authored=CourseLesson.model_validate({k:result[k] for k in CourseLesson.model_fields}).model_dump();unit=authored['units'][0]
    purposes={q['purpose'] for q in unit['quiz']}
    if not {'understanding','practice','debug'}<=purposes:raise ValueError('Include understanding, practice and a reproducible debug question in the topic check.')
    plain={**authored,'evidence_quotes':result['evidence_quotes'],'units':[{k:unit[k] for k in Unit.model_fields}]}
    plain_unit=plain['units'][0]
    plain_unit['quiz']=[{k:q[k] for k in QuizQuestion.model_fields} for q in unit['quiz']]
    plain_unit['prediction']={k:unit['prediction'][k] for k in Prediction.model_fields}
    plain_unit['exercise']={k:unit['exercise'][k] for k in Exercise.model_fields}
    source_ids=[c['id'] for c in chunks]
    checked=await validate_lesson(plain,execution,source_ids,chunks,WideLesson);target=checked['units'][0]
    for raw,question in zip(unit['quiz'],target['quiz']):
        code=raw['code'];sources=[code.replace('___',o) for o in raw['options']] if raw['kind']=='complete_code' else [code] if code else []
        policy.tags(raw,concept,sources)
        question.update({k:raw[k] for k in ('needs','targets','purpose','bug_option_index','expected_bug_output')})
        if raw['purpose']=='debug':
            bug=raw['bug_option_index']
            if raw['kind']!='complete_code' or bug is None or bug>=len(raw['options']) or bug==raw['answer_index']:raise ValueError('A debug question needs one identified buggy distractor and a different verified fix.')
            code=raw['code'].replace('___',raw['options'][bug]);run=await checked_run(execution,code,None,[[]]);case=run['cases'][0]
            observed=case['error']['type'] if case.get('error') else case.get('output','').strip()
            if observed!=raw['expected_bug_output'].strip() or observed==raw['expected_output'].strip():raise ValueError('The declared bug does not reproduce as described, or its fix changes nothing.')
            question['bug_verification']={'observed':observed,'fixed_output':raw['expected_output'],'basis':'Bug reproduced and distinct fix passed actual Python'}
    for name in ('prediction','exercise'):
        raw=unit[name];source=[raw['code']] if name=='prediction' else [raw['reference_solution']]
        policy.tags(raw,concept,source);target[name].update({k:raw[k] for k in ('needs','targets')})
        if name=='exercise':target[name]['required_helpers']=raw.get('required_helpers',[])
    fresh=await validate_exercise(unit['fresh_exercise'],execution,source_ids)
    fresh.update({k:unit['fresh_exercise'][k] for k in ('needs','targets','required_helpers')});policy.tags(fresh,concept,[fresh['reference_solution']]);policy.check_exercise(fresh,concept)
    if fresh['cases']==target['exercise']['cases'] or fresh['instructions']==target['exercise']['instructions']:raise ValueError('The frozen fresh task must use different inputs and a changed context or requirement.')
    target['fresh_exercise']=fresh
    policy.check_lesson(checked,concept)
    for exercise in (target['exercise'],fresh):
        policy.require_target(exercise['reference_solution'],concept,exercise)
        if concept=='scope':
            observed=await checked_run(execution,exercise['reference_solution'],exercise['entry'],[case['arguments'] for case in exercise['cases']],exercise)
            policy.require_target(exercise['reference_solution'],concept,exercise,observed['cases'][0].get('events',[]))
    examples=list(policy.code_blocks(checked['answer']+'\n'+target['explanation']))
    if len(examples)<2:raise ValueError('Include at least two complete original worked examples in the notes.')
    for code in examples:
        run=await checked_run(execution,code,None,[[]])
        if run['cases'][0].get('error'):raise ValueError('A worked note example does not run. Put deliberately buggy code in the checked debug questions instead.')
    checked['course_validation']={'concept':concept,'worked_examples_run':len(examples),'quiz_questions':len(target['quiz'])+1,'debug_questions_reproduced':sum(q['purpose']=='debug' for q in target['quiz']),
        'practice_cases':target['exercise']['verification']['cases'],'fresh_cases':fresh['verification']['cases'],'scope':'Execution, prerequisite tags and source-wording checks; conceptual answers and teaching quality need review.'}
    from .course_rubrics import verify_oracle
    checked['rubric_validation']=await verify_oracle(concept,execution)
    if result.get('claim_review'):checked['claim_review']=result['claim_review']
    return checked


COURSE_INSTRUCTION='''Write one original beginner Python lesson for the specified concept using only the supplied source passages. This will become a shared, versioned base course after operator review, not a per-student summary. Write original explanations; cite the source ideas with short exact anchors rather than copying their wording into the notes. Return one unit only. In answer write readable Markdown notes with at least two complete small standalone python code fences, showing the origin of every input and variable. All note examples must execute without errors; explain actual flow and common mistakes. Put deliberate errors only in debug checks.
Create four to six short topic-check questions plus the separate output prediction: understanding from notes, applying the practice idea, common mistakes, and at least one debug question. Tag every question/prediction/task with needs (its prerequisite concepts) and targets (only the current concept). Do not put the current target in needs. Concept questions use kind concept, optionally complete runnable context, and empty expected_output. Completion/debug questions use kind complete_code, exactly one ___ in a complete program, three or four valid Python single-line replacement options, one answer_index and its exact expected printed output. For purpose debug also name bug_option_index, a different wrong option whose real error/output is expected_bug_output. The bug must reproduce and the corrected option must pass. Other questions use null bug_option_index and empty expected_bug_output. Never hide literal values or collection setup in the prose prompt; put it in code. The separate prediction has three distinct output strings with one exact matching expected_output.
Provide main exercise and a genuinely different fresh_exercise. Before the functions unit both use kind program: parameters is an ordered list of input-variable names populated separately for each check, entry names a DIFFERENT result variable to assign. Learner code is ordinary top-level statements, never a def/return wrapper. Explain all input meanings and include one example set of supplied inputs, but do not reset those input variables in starter/reference. Cases arguments correspond to parameters. Use three or four varied checks including a boundary; the unfinished starter must fail at least one. Reference solution must actually use the target concept. Preserve_input means do not mutate supplied input collections; local names may be rebound. A fresh task should state its goal, inputs and output contract without solving the key reasoning step or telling the learner which range/condition expression to write. Main and fresh must use different check inputs and contexts. Keep programs short, supported by the bounded runner. No imports, comprehensions, slices, input, f-strings, sets, exceptions, annotations, classes or unsupported methods. No claim of mastery or learning gains. The application will run all programs and reject untaught constructs, bad source quotes, mismatched outputs and unreproduced bugs.'''
