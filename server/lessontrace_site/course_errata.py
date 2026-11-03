"""Hash-bound wording corrections over immutable v2 sources; grading code is untouched."""
from __future__ import annotations
import copy
import hashlib

VERSION='course-wording-errata-v2'
PATCHES={
    'nested_data':{'source_sha256':'734824e65f43ecacca1760448beb3797458b804e71b624c8f89ed7b62c140f82',
        'path':['units',0,'fresh_exercise','instructions'],'old':'"corner": (4, 7)','new':'"corner": [4, 7]',
        'reason':'The exercise supplies a list; its illustrative literal must also be a list.'},
    'boolean_logic':{'source_sha256':'829ebc0f8459f43e5323436bb6df6c147633d36f0dbc65dfc768ffa564e51136',
        'path':['units',0,'quiz',3,'explanation'],
        'old':'7 is between the limits, so the outside test is False. The bug joins outside tests with and, which cannot catch low-side values.',
        'new':'The shown x is 12, above high = 10, so x > high is True and the outside test using or prints alarm. The buggy and condition requires both outside comparisons at once and misses this value.',
        'reason':'The explanation must follow the displayed input x = 12, not an earlier example value.'},
    'range':{'source_sha256':'ab6609ab437d7a7bb14857022db3535bdf60e89115c84f6421b5c0d347911701',
        'edits':[
            {'path':['answer'],'old':'- Starting at `1` when you need index `0`. Bare `range(n)` always starts at `0`.',
                'new':'- Starting at `1` when you need index `0`. Bare `range(n)` always starts at `0`.\n\n### When the range is empty\n\nIf no value meets the range bounds, the loop body runs zero times. In `range(2, 2)`, the start already equals the excluded stop, so there is no first value. The list below stays empty because the append line is never reached:\n\n```python\nvalues = []\nfor n in range(2, 2):\n    values.append(n)\nprint(values)\n```\n\n```text\n[]\n```\n\nThe same zero-iteration rule applies to `range(0)`. An empty range does not run the body once with the stop value.'},
            {'path':['evidence_quotes',1,'claim'],'old':'range(n) starts at 0 and does not go through n.',
                'new':'The end number passed to range is excluded.'}],
        'reason':'Teach the empty-range boundary explicitly and keep the caption claim within what its quoted words support.'}}


def edits(patch):return patch['edits'] if 'edits' in patch else [patch]


def apply(artifact,raw):
    patch=PATCHES.get(artifact.get('concept_id'))
    if artifact.get('version')!='python-fundamentals-v2' or not patch:return artifact
    if hashlib.sha256(raw).hexdigest()!=patch['source_sha256']:raise ValueError('This wording correction does not match the immutable source revision.')
    result=copy.deepcopy(artifact)
    for change in edits(patch):
        parent=result['curriculum']
        for key in change['path'][:-1]:parent=parent[key]
        key=change['path'][-1]
        if parent[key].count(change['old'])!=1:raise ValueError('The wording correction no longer matches its original text.')
        parent[key]=parent[key].replace(change['old'],change['new'])
    result['course_wording_revision']={'version':VERSION,'source_sha256':patch['source_sha256'],'reason':patch['reason'],
        'review':'Operator correction with AI assistance; not human teacher approval. No grading code or expected answer changed.'}
    return result


def update_record(record,artifact):
    """Only approved wording fields change; saved attempts, code and grading evidence stay owned."""
    patch=PATCHES.get(record.get('course_concept'))
    if not patch or not artifact.get('course_wording_revision') or record.get('course_version')!='python-fundamentals-v2':return record
    result=copy.deepcopy(record)
    for change in edits(patch):
        source=artifact['curriculum'];target=result['curriculum']
        for key in change['path'][:-1]:source=source[key];target=target[key]
        target[change['path'][-1]]=source[change['path'][-1]]
        if change['path']==['answer']:result['answer']=artifact['curriculum']['answer']
    result['course_wording_revision']=artifact['course_wording_revision']
    return result


def update_variants(progress,record):
    """Correct only a copied frozen task's wording; do not change answers or attempts."""
    if record.get('course_concept')!='nested_data' or not record.get('course_wording_revision'):return progress
    result=copy.deepcopy(progress)
    for unit in record['curriculum']['units']:
        fixed=unit.get('fresh_exercise',{})
        for variant in result.get('units',{}).get(unit['id'],{}).get('variants',{}).values():
            exercise=variant.get('exercise',{})
            if variant.get('frozen') and all(exercise.get(key)==fixed.get(key) for key in ('entry','cases','reference_solution')):
                exercise['instructions']=fixed['instructions']
    return result
