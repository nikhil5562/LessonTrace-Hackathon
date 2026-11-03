"""Reference programs and deliberate common errors are independent of generated cases."""
import asyncio
import copy

import pytest
from test_pilot import runtime
from lessontrace_site.course_catalog import TOPICS
from lessontrace_site import course_rubrics


def test_every_topic_has_separate_criteria_prerequisites_and_honest_review_status():
    assert set(course_rubrics.RUBRICS)==set(TOPICS) and not course_rubrics.AUTHORSHIP['human_teacher_approved']
    for concept,item in TOPICS.items():
        rubric=course_rubrics.rubric_for(concept)
        assert rubric['prerequisites']==item['needs'] and len(rubric['criteria'])>=2
        assert len({c['id'] for c in rubric['criteria']})==len(rubric['criteria'])
        assert rubric['oracle']['source']!=rubric['oracle']['mutant_source']


@pytest.mark.parametrize('concept',list(TOPICS))
def test_independent_reference_program_and_common_error_are_distinguished(runtime,concept):
    result=asyncio.run(course_rubrics.verify_oracle(concept,runtime))
    assert result['oracle_passed'] and result['mutant_rejected'] and not result['human_teacher_approved']


def test_an_incorrect_reference_answer_cannot_be_self_certified(runtime,monkeypatch):
    broken=copy.deepcopy(course_rubrics.RUBRICS['break']);broken['oracle']['expected_output']='WRONG'
    monkeypatch.setitem(course_rubrics.RUBRICS,'break',broken)
    with pytest.raises(ValueError,match='specified result'):asyncio.run(course_rubrics.verify_oracle('break',runtime))
