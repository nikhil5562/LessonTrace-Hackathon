"""Versioned wording-only corrections preserve immutable content and learner evidence."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from lessontrace_site import course_errata
from lessontrace_site.video_quiz import questions

ROOT=Path(__file__).resolve().parents[2]/'course_content/python-fundamentals-v2'


@pytest.mark.parametrize('concept',list(course_errata.PATCHES))
def test_errata_are_hash_bound_and_change_only_the_named_wording_field(concept):
    raw=(ROOT/(concept+'.json')).read_bytes();original=json.loads(raw)
    corrected=course_errata.apply(original,raw)
    assert hashlib.sha256(raw).hexdigest()==course_errata.PATCHES[concept]['source_sha256']
    assert json.loads(raw)==original and (ROOT/(concept+'.json')).read_bytes()==raw
    restored=copy.deepcopy(corrected);restored.pop('course_wording_revision')
    for change in course_errata.edits(course_errata.PATCHES[concept]):
        parent=restored['curriculum'];old=original['curriculum'];path=change['path']
        for field in path[:-1]:parent=parent[field];old=old[field]
        assert parent[path[-1]]!=old[path[-1]]
        parent[path[-1]]=old[path[-1]]
    assert restored==original
    with pytest.raises(ValueError,match='immutable source'):course_errata.apply(original,raw+b' ')
    assert [q['question_hash'] for q in questions(original['curriculum']['units'][0])]==[q['question_hash'] for q in questions(corrected['curriculum']['units'][0])]


def test_corrected_wording_follows_the_displayed_values_and_types():
    values={c:course_errata.apply(json.loads((ROOT/(c+'.json')).read_bytes()),(ROOT/(c+'.json')).read_bytes()) for c in course_errata.PATCHES}
    assert '"corner": [4, 7]' in values['nested_data']['curriculum']['units'][0]['fresh_exercise']['instructions']
    text=values['boolean_logic']['curriculum']['units'][0]['quiz'][3]['explanation']
    assert 'x is 12' in text and 'prints alarm' in text and '7 is between' not in text
    assert 'When the range is empty' in values['range']['curriculum']['answer']
    assert values['range']['curriculum']['evidence_quotes'][1]['claim']=='The end number passed to range is excluded.'


def test_existing_record_and_copied_frozen_task_keep_owned_work():
    raw=(ROOT/'nested_data.json').read_bytes();artifact=json.loads(raw);fixed=course_errata.apply(artifact,raw)
    record={'course_version':'python-fundamentals-v2','course_concept':'nested_data','curriculum':copy.deepcopy(artifact['curriculum']),'lesson_id':'owned-id','draft':'my code'}
    unit=record['curriculum']['units'][0]
    progress={'units':{unit['id']:{'quiz_history':[{'correct':False}],'variants':{'fresh':{'frozen':True,'exercise':copy.deepcopy(unit['fresh_exercise']),'id':'same-id'}}}},'attempts':['saved-run'],'code':'my code'}
    corrected=course_errata.update_record(record,fixed);updated=course_errata.update_variants(progress,corrected)
    assert corrected['lesson_id']==record['lesson_id'] and corrected['draft']==record['draft']
    assert updated['attempts']==progress['attempts'] and updated['code']==progress['code']
    assert updated['units'][unit['id']]['quiz_history']==progress['units'][unit['id']]['quiz_history']
    old=progress['units'][unit['id']]['variants']['fresh']['exercise'];new=updated['units'][unit['id']]['variants']['fresh']['exercise']
    assert old|{'instructions':new['instructions']}==new and old['instructions']!=new['instructions']
    assert course_errata.update_record(record|{'course_version':'python-fundamentals-v1'},fixed)==record|{'course_version':'python-fundamentals-v1'}
