"""Readable walkthrough tables without interpreting model text as HTML."""
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import pytest

from test_video_startup import record
from lessontrace_site.note_exports import blocks,export_notes

ROOT=Path(__file__).resolve().parents[2]
TABLE='| Outer value | Inner value | Next action |\n|---|---|---|\n| A | 1 | Print `letter` |\n| A | 2 | `break`, then outer-body print |'


def test_exported_table_steps_keep_headers_and_each_row():
    result=blocks(TABLE)
    assert [row.kind for row in result]==['bullet','bullet']
    assert result[0].text=='**Outer value:** A; **Inner value:** 1; **Next action:** Print `letter`'
    assert '**Inner value:** 2' in result[1].text and 'outer-body print' in result[1].text


def test_escaped_pipes_stay_in_cells_and_code_fences_stay_code():
    result=blocks('| Value | Meaning |\n|---|---|\n| `A\\|B` | A separator |')
    assert len(result)==1 and '`A|B`' in result[0].text
    result=blocks('```python\n'+TABLE+'\n```')
    assert len(result)==1 and result[0].kind=='code' and result[0].text==TABLE


def test_pipe_prose_without_table_separator_remains_prose():
    result=blocks('Value | Meaning\nnot a table')
    assert len(result)==1 and result[0].kind=='paragraph'


def test_word_and_pdf_keep_walkthrough_rows_readable():
    source=record('a'*32);source['answer']='## Follow the shown example\n\n'+TABLE
    document,_,_=export_notes(source,'docx')
    with ZipFile(BytesIO(document)) as archive:
        text=archive.read('word/document.xml').decode()
    assert 'Outer value:' in text and 'Inner value:' in text and 'outer-body print' in text and '|---|' not in text
    pdf,_,_=export_notes(source,'pdf');assert pdf.startswith(b'%PDF')


def test_actual_notes_renderer_preserves_table_semantics_sources_and_literal_html():
    node=os.environ.get('LESSONTRACE_NODE') or shutil.which('node');jsdom=ROOT/'.local/frontend-check/node_modules/jsdom/lib/api.js'
    if not node or not jsdom.is_file():pytest.skip('Node and optional jsdom required')
    result=subprocess.run([node,str(Path(__file__).with_name('note_tables.mjs')),str(ROOT),str(jsdom)],capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
