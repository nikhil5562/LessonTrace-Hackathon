import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'))
from lessontrace_site.main import create_app
from lessontrace_site.video_lessons import video_id,source_chunks
from lessontrace_site import video_lessons


class IdleRunner:
    ready,error=True,None
    async def warmup(self):pass
    async def close(self):pass


class FakeMeta:
    enabled=True
    def __init__(self):self.calls=[]
    async def generate(self,instruction,evidence,source_ids):
        self.calls.append(evidence)
        assert 'caption_chunks' in evidence and 'images' not in evidence
        return {'answer':'A function returns a result to its caller.','sources':source_ids[:1],'provider':'meta','model':'synthetic-test-model'}


@pytest.fixture
def video_browser(tmp_path,monkeypatch):
    record={'video_id':'fz_BCnhEQYQ','origin':'Synthetic public-caption fixture','language':'en','is_generated':True,'snippets':[{'text':'Functions take arguments.','start':0,'duration':5},{'text':'Return gives a result.','start':121,'duration':5}]}
    monkeypatch.setattr(video_lessons,'fetch_captions',lambda identifier,cache:record)
    provider=FakeMeta()
    app=create_app(tmp_path,runner=IdleRunner(),provider=provider)
    with TestClient(app) as client:
        client.headers['X-LessonTrace-CSRF']=client.get('/api/session').json()['csrf']
        yield client,provider


@pytest.mark.parametrize('url',['http://127.0.0.1/private','https://youtube.com.evil.test/watch?v=fz_BCnhEQYQ','https://user:password@www.youtube.com/watch?v=fz_BCnhEQYQ','https://www.youtube.com/watch?v=fz_BCnhEQYQ&v=abcdefghijk'])
def test_video_parser_rejects_other_destinations(url):
    with pytest.raises(ValueError):video_id(url)


def test_video_parser_accepts_shared_and_watch_links():
    assert video_id('https://youtu.be/fz_BCnhEQYQ?si=example')=='fz_BCnhEQYQ'
    assert video_id('https://www.youtube.com/watch?list=example&v=fz_BCnhEQYQ&t=30')=='fz_BCnhEQYQ'


def test_consent_and_source_failure_make_no_model_request(video_browser,monkeypatch):
    client,provider=video_browser
    body={'url':'https://youtu.be/fz_BCnhEQYQ','consent':False}
    assert client.post('/api/video-session',json=body).status_code==409
    assert not provider.calls
    def unavailable(*args):raise RuntimeError('synthetic unavailable captions')
    monkeypatch.setattr(video_lessons,'fetch_captions',unavailable)
    body['consent']=True
    assert client.post('/api/video-session',json=body).status_code==503
    assert not provider.calls
    assert client.get('/api/session').json()['meta']['allowance']['remaining_requests']==10


def test_notes_use_timed_sources_and_stay_private(video_browser):
    client,provider=video_browser
    result=client.post('/api/video-session',json={'url':'https://youtu.be/fz_BCnhEQYQ','consent':True})
    assert result.status_code==200,result.text
    record=result.json()['session']
    assert record['practice_topic']=='functions' and record['auto_generated']
    assert record['source_segments'][1]['start']==121
    assert 'caption_chunks' not in record
    assert provider.calls[0]['caption_chunks'][0]['text']=='Functions take arguments.'
    assert client.get('/api/video-session').json()['session']['answer']==record['answer']
    client.cookies.clear()
    client.get('/api/session')
    assert client.get('/api/video-session').json()['session'] is None


def test_manual_captions_need_review_and_have_no_invented_timestamps(video_browser):
    client,provider=video_browser
    body={'url':'https://youtu.be/fz_BCnhEQYQ','consent':True,'caption_text':'My accessible caption excerpt.'}
    assert client.post('/api/video-session',json=body).status_code==409
    body['caption_reviewed']=True
    data=client.post('/api/video-session',json=body).json()['session']
    assert data['source_segments'][0]['start'] is None
    assert 'unverified' in data['caption_source']


def test_video_range_is_bounded_before_model_use(video_browser):
    client,provider=video_browser
    result=client.post('/api/video-session',json={'url':'https://youtu.be/fz_BCnhEQYQ','consent':True,'start_seconds':200,'end_seconds':100})
    assert result.status_code==422 and not provider.calls
    with pytest.raises(ValueError,match='shorter'):
        source_chunks('fz_BCnhEQYQ',{'snippets':[{'start':0,'duration':1,'text':'x'*18000}]})


def test_unknown_inline_caption_reference_is_not_saved(video_browser,monkeypatch):
    client,provider=video_browser
    async def invalid_reference(*args):
        return {'answer':'A result. [video-other-source]','sources':['video-fz_BCnhEQYQ-0'],'provider':'meta','model':'synthetic-test-model'}
    monkeypatch.setattr(provider,'generate',invalid_reference)
    response=client.post('/api/video-session',json={'url':'https://youtu.be/fz_BCnhEQYQ','consent':True})
    assert response.status_code==503
    assert 'not saved' in response.json()['detail']
    assert client.get('/api/video-session').json()['session'] is None


def test_dictionary_video_opens_related_original_practice(video_browser,monkeypatch):
    client,provider=video_browser
    monkeypatch.setattr(video_lessons,'fetch_captions',lambda identifier,cache:{'video_id':identifier,'origin':'Synthetic caption fixture','language':'en','is_generated':False,'snippets':[{'text':'Dictionary keys identify values.','start':0,'duration':5}]})
    response=client.post('/api/video-session',json={'url':'https://youtu.be/4t10v2QmTHU?si=example','consent':True})
    assert response.status_code==200,response.text
    record=response.json()['session']
    assert record['practice_topic']=='dictionary'
    assert record['title']=='Python Dictionaries · Visually Explained'
    assert 'authored separately' in record['practice_basis']
    assert provider.calls[0]['caption_chunks'][0]['id']=='video-4t10v2QmTHU-1'


def test_exhausted_allowance_cannot_make_a_model_request(video_browser):
    client,provider=video_browser
    for _ in range(10):client.app.state.store.reserve_provider('synthetic-owner','Synthetic prior reservation')
    response=client.post('/api/video-session',json={'url':'https://youtu.be/4t10v2QmTHU','consent':True})
    assert response.status_code==429 and not provider.calls
    assert client.get('/api/session').json()['meta']['allowance']['remaining_requests']==0


@pytest.mark.parametrize('format',['pdf','docx','md'])
def test_note_downloads_preserve_sources_without_provider_calls(video_browser,format):
    from io import BytesIO
    from zipfile import ZipFile
    client,provider=video_browser
    record=client.post('/api/video-session',json={'url':'https://youtu.be/fz_BCnhEQYQ','consent':True}).json()['session']
    calls=len(provider.calls)
    before=client.get('/api/session').json()['meta']['allowance']
    response=client.get('/api/video-session/download/'+format,params={'expected_revision':record['revision']})
    assert response.status_code==200,response.text[:300]
    assert 'attachment;' in response.headers['content-disposition']
    assert 'functions-codebasics-notes.'+format in response.headers['content-disposition']
    assert response.headers['cache-control']=='no-store'
    if format=='pdf':
        assert response.content.startswith(b'%PDF-') and b'/URI' in response.content
    elif format=='docx':
        with ZipFile(BytesIO(response.content)) as archive:
            text=archive.read('word/document.xml').decode()
            rels=archive.read('word/_rels/document.xml.rels').decode()
            assert 'A function returns a result' in text
            assert 'watch?v=fz_BCnhEQYQ&amp;t=0' in rels
            assert not any('vbaProject' in name for name in archive.namelist())
    else:
        assert 'Audio and video frames were not analysed separately' in response.text
        assert '[video-' not in response.text
    assert len(provider.calls)==calls
    assert client.get('/api/session').json()['meta']['allowance']==before


def test_download_checks_ownership_revision_and_format(video_browser):
    client,provider=video_browser
    record=client.post('/api/video-session',json={'url':'https://youtu.be/fz_BCnhEQYQ','consent':True}).json()['session']
    path='/api/video-session/download/'
    assert client.get(path+'pdf',params={'expected_revision':'0'*64}).status_code==409
    assert client.get(path+'exe',params={'expected_revision':record['revision']}).status_code==422
    assert client.get(path+'pdf',params={'expected_revision':'not-a-revision'}).status_code==422
    client.cookies.clear();client.get('/api/session')
    assert client.get(path+'pdf',params={'expected_revision':record['revision']}).status_code==404


def test_export_parser_keeps_code_and_html_literal():
    from io import BytesIO
    from zipfile import ZipFile
    from xml.etree import ElementTree
    from lessontrace_site.note_exports import export_notes,blocks
    answer='## A heading\n\n**Keys** use `values`. <script>alert(1)</script>\n\n```python\nvalues = {"<tag>": 1}\nprint(values)\n```\n'
    record={'title':'Safe\r\nTitle: Notes','video_id':'fz_BCnhEQYQ','answer':answer,'sources':['video-fz_BCnhEQYQ-1'],'caption_chunks':[{'id':'video-fz_BCnhEQYQ-1','start':12.5,'text':'Synthetic captions.'}]}
    assert next(b.text for b in blocks(answer) if b.kind=='code')=='values = {"<tag>": 1}\nprint(values)'
    content,name,_=export_notes(record,'docx')
    assert '\r' not in name and '\n' not in name and ':' not in name
    with ZipFile(BytesIO(content)) as archive:
        root=ElementTree.fromstring(archive.read('word/document.xml'))
        text=''.join(root.itertext())
        assert '<script>alert(1)</script>' in text and 'values = {"<tag>": 1}' in text
    content,_,_=export_notes(record,'pdf')
    assert content.startswith(b'%PDF-')
