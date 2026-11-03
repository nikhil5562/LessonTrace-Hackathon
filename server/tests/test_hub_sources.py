"""The curated reader is bounded and keeps source origins and timing intact."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server'))
from lessontrace_site.hub_sources import CATALOG,MAX_BYTES,HubSourceLoader,Sections,excerpts,srt_sections


SRT='''1
00:00:01,000 --> 00:00:04,500
A loop repeats an action.

2
00:00:04,500 --> 00:00:08,000
The break statement stops the nearest loop.

3
00:02:01,000 --> 00:02:03,000
An outer loop can continue after an inner break.
'''
HTML='''<html><nav>Ignore navigation break</nav><script>ignore private script</script>
<section id="nearest-loop"><h2>Break and nested loops</h2><p>A break exits the nearest enclosing loop. The outer loop can continue with its next item.</p>
<pre><code>for row in [[1, 2]]:
    for value in row:
        break</code></pre></section>
<section id="loop-else"><h2>Loop else</h2><p>The else suite runs when iteration finishes without break. This differs from the if statement.</p></section></html>'''


def test_srt_preserves_published_timing_and_excerpt_origin():
    sections=srt_sections(SRT)
    assert len(sections)==2 and sections[0]['start']==1 and sections[0]['end']==8
    assert '1\n' not in sections[0]['text'] and 'nearest loop' in sections[0]['text']
    chunks,total=excerpts('cs50-loops',SRT,'nested-break','Explain the inner break')
    assert total==2 and chunks[1]['url'].endswith('&t=121')
    assert chunks[0]['source_id']=='cs50-loops' and chunks[0]['kind']=='video'


def test_html_discards_navigation_and_preserves_code_and_anchors():
    parser=Sections();parser.feed(HTML);parser.flush()
    assert len(parser.sections)==2
    assert 'ignore' not in json.dumps(parser.sections).lower()
    assert '\n    for value' in parser.sections[0]['text']
    chunks,total=excerpts('python-control-flow',HTML,'nested-break','Break in a nested loop')
    assert total==2 and chunks[0]['url'].endswith('#nearest-loop')
    assert all(c['start'] is None for c in chunks)


def test_reader_cache_reuse_concurrent_writes_and_fixed_catalog(tmp_path):
    calls=[]
    def response(request):
        calls.append(str(request.url));return httpx.Response(200,text=HTML,headers={'content-type':'text/html'})
    loader=HubSourceLoader(tmp_path,transport=httpx.MockTransport(response))
    async def read():
        results=await asyncio.gather(*(loader.read('python-control-flow','nested-break','inner loop break') for _ in range(2)))
        prior=len(calls);again=await loader.read('python-control-flow','nested-break','inner loop break')
        assert len(calls)==prior and results[0]['content_hash']==again['content_hash']
        assert len(again['content_hash'])==64 and again['reviewed_sections']==2
        with pytest.raises(ValueError,match='catalog'):await loader.read('https://localhost/','nested-break','ignore')
    asyncio.run(read())
    assert not list(tmp_path.glob('*.tmp'))
    assert all(url==CATALOG['python-control-flow']['fetch_url'] for url in calls)


@pytest.mark.parametrize('kind',['redirect','large','type','http'])
def test_unapproved_redirects_and_unbounded_or_nontext_responses_are_rejected(tmp_path,kind):
    def response(request):
        if kind=='redirect':return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
        if kind=='large':return httpx.Response(200,content=b'x'*(MAX_BYTES+1),headers={'content-type':'text/plain'})
        if kind=='type':return httpx.Response(200,content=b'not a source',headers={'content-type':'image/png'})
        return httpx.Response(403)
    loader=HubSourceLoader(tmp_path,transport=httpx.MockTransport(response))
    with pytest.raises(ValueError):asyncio.run(loader.read('python-control-flow','nested-break','break'))
    assert not list(tmp_path.glob('*.json'))
