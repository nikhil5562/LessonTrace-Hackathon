"""Audit context must preserve passage identity, anchors and frozen source hashes."""
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('lessontrace_course_audit',ROOT/'scripts/review_frozen_course.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


@pytest.mark.parametrize('fault',[None,'different_text','different_section','different_time','different_offset','different_source','different_id'])
def test_audit_expansion_requires_the_same_passage_and_all_original_anchors(fault):
    saved={'id':'hub-python-introduction-0001','source_id':'python-introduction','heading':'Numbers','start':None,'source_offset':0,'text':'Original short anchor.'}
    candidate=copy.deepcopy(saved)|{'text':'Additional public context. Original short anchor. More supporting text.'}
    changes={'different_text':('text','The original anchor is absent.'),'different_section':('heading','Strings'),
        'different_time':('start',120),'different_offset':('source_offset',2700),'different_source':('source_id','other-source'),'different_id':('id','hub-other-0001')}
    if fault:key,value=changes[fault];candidate[key]=value
    class Reader:
        async def read(self,*args):return {'id':'python-introduction','content_hash':'evidence-hash','chunks':[candidate]}
    artifact={'source_documents':[{'id':'python-introduction'}],'caption_chunks':[saved],
        'curriculum':{'evidence_quotes':[{'source_id':saved['id'],'quote':'Original short anchor.'}]}}
    original=copy.deepcopy(artifact);chunks,report=asyncio.run(audit.expand_sources(artifact,'arithmetic',Reader()))
    assert artifact==original
    if fault:assert chunks==[saved] and report['expanded_passages']==0
    else:assert chunks==[candidate] and report['expanded_passages']==1


def test_modified_base_cannot_enter_an_audit_before_any_execution_or_api_call(tmp_path,monkeypatch):
    concept='variables';source=ROOT/'course_content'/audit.VERSION/(concept+'.json');raw=source.read_bytes()
    frozen=tmp_path/'course_content'/audit.VERSION;frozen.mkdir(parents=True)
    (frozen/(concept+'.json')).write_bytes(raw+b' ')
    (frozen/'manifest.json').write_text(json.dumps({'version':audit.VERSION,'lessons':{concept:{'file':concept+'.json','sha256':hashlib.sha256(raw).hexdigest()}}}))
    monkeypatch.setattr(audit,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='frozen course manifest'):asyncio.run(audit.packs(None,[concept]))
