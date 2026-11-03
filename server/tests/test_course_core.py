"""Actual program execution and concept gates, independent of any live provider."""
import asyncio
import copy
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'server'))
from lessontrace_site import course_catalog as catalog,course_policy as policy
from lessontrace_site.video_curriculum import validate_exercise
from lessontrace_site.teaching_quality import check_note_walkthrough
from test_pilot import runtime


def program():
    return {'kind':'program','parameters':['left','right'],'entry':'result','title':'Add the supplied values','instructions':'Assign their sum to result. Inputs left and right are supplied for each check.','starter':'result = 0',
        'reference_solution':'result = left + right','preserve_input':True,'sources':['hub-test'],
        'cases':[{'arguments':[1,2],'expected':3},{'arguments':[4,5],'expected':9},{'arguments':[-3,3],'expected':0}]}


def test_program_inputs_and_result_keep_original_source_lines(runtime):
    exercise=program();checked=asyncio.run(validate_exercise(exercise,runtime,['hub-test']))
    assert checked['kind']=='program'
    raw=asyncio.run(runtime.execute({'source':exercise['reference_solution'],'entry':None,'arguments':[[7,8]],'program_inputs':['left','right'],'result_name':'result','trace_case':0}))
    case=raw['cases'][0];assert case['actual']==15 and case['arguments_after']==[7,8]
    event=case['events'][-1];assert event['line']==1 and any(f['bindings'].get('left') for f in event['frames'])
    assert all(f['name']=='<module>' for f in event['frames'])


def test_topic_windows_retain_late_length_explanation_in_long_source_section():
    from lessontrace_site.hub_sources import excerpts
    html='<h2 id="text">Text</h2><p>'+('intro ' * 600)+'The length is obtained with len(example).</p>'
    catalog={'reference':{'kind':'web','title':'Controlled reference','url':'https://example.test/python'}}
    chunks,_=excerpts('reference',html,'strings','length',catalog,{'sections':['text'],'text_windows':{'text':[0,3000]}})
    assert len(chunks)==2 and any('len(example)' in c['text'] for c in chunks)
    assert {c['source_offset'] for c in chunks}=={0,3000} and all(c['truncated'] for c in chunks)
    assert len({c['id'] for c in chunks})==2


def test_function_introduction_allows_one_parameter_before_multiple_default_arguments():
    policy.check_code('def adjust(value):\n    return value + 2','functions')
    with pytest.raises(ValueError,match='parameters'):policy.check_code('def adjust(value, extra=2):\n    return value + extra','functions')
    policy.check_code('def adjust(value, extra=2):\n    return value + extra','parameters')


def test_scope_task_requires_observed_helper_frames_not_only_equal_arithmetic(runtime):
    helpers='def add_fee(amount):\n    return amount + 5\ndef double_it(amount):\n    return amount * 2\n'
    correct=helpers+'def make_total(amount):\n    return add_fee(amount) + double_it(amount)'
    dead=helpers+'def make_total(amount):\n    return amount * 3 + 5\n    add_fee(amount)\n    double_it(amount)'
    spec={'required_helpers':['add_fee','double_it']}
    def observe(source):return asyncio.run(runtime.execute({'source':source,'entry':'make_total','arguments':[[2],[0],[-1]],'trace_case':0}))
    checked=observe(correct);bypassed=observe(dead)
    assert [c['actual'] for c in checked['cases']]==[c['actual'] for c in bypassed['cases']]==[11,5,2]
    policy.require_target(correct,'scope',spec,checked['cases'][0]['events'])
    with pytest.raises(ValueError,match='helper'):policy.require_target(dead,'scope',spec,bypassed['cases'][0]['events'])


@pytest.mark.parametrize('inputs,result',[(['__builtins__'],'result'),(['print'],'result'),(['value'],'value'),(['value'],'_private')])
def test_program_input_namespace_cannot_override_runner_capabilities(runtime,inputs,result):
    raw=asyncio.run(runtime.execute({'source':'result = 1','entry':None,'arguments':[[2]],'program_inputs':inputs,'result_name':result}))
    assert raw.get('error',{}).get('type')=='Unsupported'


def test_prerequisites_are_concepts_not_course_completion():
    assert len(catalog.outline())==5 and len(catalog.outline()[3]['topics'])==9
    assert 'if_else' not in catalog.allowed_concepts('for_loop')
    assert {'for_loop','if_else','lists'}<=catalog.allowed_concepts('loop_if_else')
    question={'needs':['for_loop','if_else','lists'],'targets':['loop_if_else']}
    assert not policy.eligible(question,{'for_loop','lists'})
    assert policy.eligible(question,{'for_loop','lists','if_else'})
    assert 'functions' not in catalog.allowed_concepts('inner_break')
    policy.check_code('result = []\nfor item in items:\n    result.append(item)','for_loop')
    with pytest.raises(ValueError,match='if_else'):policy.check_code('for item in items:\n    if item > 0:\n        print(item)','for_loop')
    with pytest.raises(ValueError,match='functions'):policy.check_code('def collect(items):\n    return items','for_loop')


def test_question_tags_cannot_hide_a_prerequisite_and_target_is_not_a_need():
    question={'needs':['for_loop'],'targets':['loop_if_else']}
    policy.tags(question,'loop_if_else',['for x in values:\n    if x > 0:\n        print(x)'])
    assert {'variables','comparisons','if_else','for_loop'}<=set(question['needs'])
    assert not policy.eligible(question,{'for_loop','variables'})
    with pytest.raises(ValueError,match='outside'):policy.tags({'needs':['loop_if_else'],'targets':['loop_if_else']},'loop_if_else')
    with pytest.raises(ValueError,match='bypass'):policy.require_target('result = values.copy()','for_loop')
    policy.require_target('for row in rows:\n    for value in row:\n        break','inner_break')


def test_displayed_output_does_not_hide_the_next_defined_example():
    text='```python\ni = 1\nprint(i)\n```\n\n```text\n1\n```\n\nWhy this happens:\n\n```python\nn = 2\nprint(n)\n```\n\nWhen `n = 2`, the shown program prints it.'
    check_note_walkthrough(text)
    assert len(list(policy.code_blocks(text)))==2
