"""Keep code premises and concrete walkthrough values tied to shown examples."""
import asyncio

import pytest

from test_video_learning import browser
from lessontrace_site.teaching_quality import check_note_walkthrough,break_targets,check_control_premise
from lessontrace_site.video_curriculum import validate_quiz


PROMPT='A break runs inside the inner loop of a nested loop. What happens next?'
NESTED='for outer in [1, 2]:\n    for inner in [10, 20]:\n        print(outer, inner)\n        break\n    print("row done")'


def question(code=NESTED,prompt=PROMPT):
    return {'kind':'concept','prompt':prompt,'code':code,'options':['Execution resumes after the inner loop','Both loops stop','The inner loop starts over immediately'],
        'answer_index':0,'expected_output':'','explanation':'The remaining outer-body print runs before the outer loop advances.','sources':['video-fixture']}


@pytest.mark.parametrize('notes',[
    'Follow the outer value. For `n = 4`, check `x = 2`; then move on. [hub-python-control-flow-0007]',
    'When `item = 10`, print it.\n\n```python\nfor item in [10, 20]:\n    print(item)\n```',
])
def test_walkthrough_rejects_values_before_their_program_setup(notes):
    with pytest.raises(ValueError,match='Explain where'):check_note_walkthrough(notes)


@pytest.mark.parametrize('notes',[
    '## The setup\n```python\nfor n in [4, 5, 6]:\n    for x in [2, 3]:\n        print(n, x)\n```\n## Follow it\nFor `n = 4`, the inner sequence starts with x at 2.',
    'Set `count = 0` to create a counter. An item can be named without asserting an unseen execution value.',
])
def test_walkthrough_accepts_introduced_names_and_non_walkthrough_prose(notes):check_note_walkthrough(notes)


def test_loop_else_break_targets_enclosing_outer_loop():
    code='for outer in [1, 2]:\n    for inner in []:\n        print(inner)\n    else:\n        break'
    assert break_targets(code)=={5:1}
    with pytest.raises(ValueError,match='nested loops'):check_control_premise(question(code),code,{'events':[]})


@pytest.mark.parametrize('code',['for i in range(2):\n    print(i)','for i in [1, 2]:\n    break',''])
def test_inner_break_question_rejects_missing_or_outer_break(browser,code):
    with pytest.raises(ValueError,match='break'):
        asyncio.run(validate_quiz([question(code)],browser[0].app.state.runner,['video-fixture']))


def test_inner_break_question_checks_actual_reached_control_and_outer_body(browser):
    checked=asyncio.run(validate_quiz([question()],browser[0].app.state.runner,['video-fixture']))[0]
    assert checked['verification']['control_premise']=={'control':'break','executed':True,'loop_depth':2}


def test_unreached_break_does_not_support_a_claim_that_it_runs(browser):
    code='for outer in [1, 2]:\n    for inner in [10, 20]:\n        if inner == 99:\n            break\n        print(inner)'
    with pytest.raises(ValueError,match='did not reach'):
        asyncio.run(validate_quiz([question(code)],browser[0].app.state.runner,['video-fixture']))


def test_general_recall_and_explicit_absence_questions_are_not_claimed_execution(browser):
    for q in [question('',prompt='Which loop does break leave?'),question('for i in range(2):\n    print(i)',prompt='Does the shown program contain a break?')]:
        checked=asyncio.run(validate_quiz([q],browser[0].app.state.runner,['video-fixture']))[0]
        assert 'control_premise' not in checked['verification']


def test_generation_repairs_mismatched_break_quiz_before_publication(browser):
    client,provider=browser;original=provider.generate
    async def generate(instruction,evidence,source_ids,**options):
        result=await original(instruction,evidence,source_ids,**options)
        if 'units' in result:
            q=question(NESTED if evidence.get('repair_request') else 'for i in range(2):\n    print(i)');q['sources']=source_ids[:1]
            result['units'][0]['quiz']=[q]
        return result
    provider.generate=generate
    response=client.post('/api/video-session/learning',json={'url':'https://youtu.be/4t10v2QmTHU','consent':True})
    assert response.status_code==200,response.text
    assert len(provider.calls)==2 and 'nested loops' in provider.calls[1]['repair_request']
    assert response.json()['learning']['unit']['quiz'][0]['code']==NESTED
