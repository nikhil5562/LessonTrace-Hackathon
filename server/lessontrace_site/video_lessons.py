"""Public-caption -> private, cited study notes. No media download or browser cookies."""
from __future__ import annotations
import asyncio
import json
import math
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from typing import Literal

from fastapi import Request, HTTPException, Response, Query
from pydantic import BaseModel, Field
from .meta import MetaUnavailable
from .note_exports import revision,export_notes


# Reviewed mappings to the original bank, not generated exercise coverage.
VIDEO_PRACTICE = {
    'fz_BCnhEQYQ': ('Functions · Codebasics', 'functions'),
    '4t10v2QmTHU': ('Python Dictionaries · Visually Explained', 'dictionary'),
}


class VideoInput(BaseModel):
    url: str = Field(min_length=1,max_length=300)
    consent: bool = False
    caption_text: str = Field(default="",max_length=18000)
    caption_reviewed: bool = False
    start_seconds: float = Field(default=0,ge=0,le=86400)
    end_seconds: float | None = Field(default=None,ge=0,le=86400)


def video_id(url):
    parsed=urlsplit(url.strip())
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in {None,443}:
        raise ValueError("Use an HTTPS YouTube watch or youtu.be link.")
    host=parsed.hostname
    if host=='youtu.be':
        identifier=parsed.path.strip('/')
    elif host in {'youtube.com','www.youtube.com','m.youtube.com'} and parsed.path=='/watch':
        identifiers=parse_qs(parsed.query).get('v',[])
        identifier=identifiers[0] if len(identifiers)==1 else ''
    else:
        identifier=''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):
        raise ValueError("Use a YouTube watch or youtu.be video link.")
    return identifier


def fetch_captions(identifier, cache):
    target=cache/(identifier+'.json')
    if target.is_file() and time.time()-target.stat().st_mtime<86400:
        result=json.loads(target.read_text(encoding='utf-8'))
        result={**result,'origin':'Cached public YouTube captions'}
    else:
        from youtube_transcript_api import YouTubeTranscriptApi
        from requests import Session
        class TimedSession(Session):
            def request(self,*args,**kwargs):
                kwargs['timeout']=10
                return super().request(*args,**kwargs)
        with TimedSession() as client:
            fetched=YouTubeTranscriptApi(http_client=client).fetch(identifier,languages=['en','en-US','en-GB'])
        result={'video_id':identifier,'language':fetched.language_code,'is_generated':fetched.is_generated,'origin':'Public YouTube caption fetch','snippets':fetched.to_raw_data()}
        cache.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result),encoding='utf-8')
    if result.get('video_id')!=identifier or not isinstance(result.get('snippets'),list) or not result['snippets'] or len(result['snippets'])>10000:
        raise ValueError('Caption data is unavailable or too large.')
    for row in result['snippets']:
        if not isinstance(row.get('text'),str) or len(row['text'])>3000 or any(not isinstance(row.get(k),(int,float)) or not math.isfinite(row[k]) or row[k]<0 for k in ('start','duration')):
            raise ValueError('Invalid caption data.')
    return result


def source_chunks(identifier,record,start=0,end=None):
    rows=[r for r in record['snippets'] if r['start']>=start and (end is None or r['start']<end)]
    if not rows:
        raise ValueError('No captions were found in the selected time range.')
    if sum(len(r['text']) for r in rows)>17500:
        raise ValueError('Choose a shorter time range under More options; this lecture exceeds the pilot context limit.')
    groups={}
    for row in rows:
        bucket=int(row['start']//120)
        groups.setdefault(bucket,[]).append(row)
    chunks=[]
    for index,group in enumerate(groups.values(),1):
        first=group[0]['start'];last=max(r['start']+r['duration'] for r in group)
        chunks.append({'id':f'video-{identifier}-{index}','start':first,'end':last,'text':' '.join(r['text'] for r in group)})
    if len(chunks)>12:
        raise ValueError('Choose a time range covering at most 24 minutes for this pilot.')
    return chunks


def public_session(record):
    if not record:return None
    curriculum=record.get('curriculum',{})
    anchors=curriculum.get('evidence_quotes',[])+(record.get('teaching_revision') or {}).get('evidence_quotes',[])
    anchors += [quote for unit in curriculum.get('units',[]) for quote in unit.get('quiz_evidence_quotes',[])]
    return {k:v for k,v in record.items() if k not in {'caption_chunks','curriculum'}} | {'revision':revision(record),'source_segments':[{k:v for k,v in chunk.items() if k!='text'} | {'excerpt':chunk['text'][:500],
        'verified_quotes':[quote for quote in anchors if quote.get('quote_verified') and quote['source_id']==chunk['id']]} for chunk in record['caption_chunks']]}


def install_video_routes(app,owner,store,meta,reserve_cloud):
    busy=set()
    cache=store.path.parent/'video-captions'

    @app.get('/api/video-session')
    async def latest(request: Request):
        return {'session':public_session(store.progress(owner(request)).get('youtube_session'))}

    @app.get('/api/video-session/download/{format}')
    async def download(format: Literal['pdf','docx','md'],request: Request,expected_revision: str=Query(pattern=r'^[a-f0-9]{64}$'),context: Literal['video','hub','course']='video'):
        record=store.progress(owner(request)).get({'hub':'hub_session','course':'course_session'}.get(context,'youtube_session'))
        if not record:raise HTTPException(404,'No saved video notes were found in this browser.')
        if expected_revision!=revision(record):raise HTTPException(409,'This lesson changed in another tab. Refresh the notes before downloading.')
        try:
            content,filename,mime=await asyncio.to_thread(export_notes,record,format)
        except ImportError:
            raise HTTPException(503,'This download format is not installed yet. Markdown is still available.') from None
        return Response(content,media_type=mime,headers={'Content-Disposition':'attachment; filename="'+filename+'"'})

    @app.post('/api/video-session')
    async def create(body: VideoInput,request: Request):
        who=owner(request,True)
        if not meta.enabled or not body.consent:
            raise HTTPException(409,'Enable Meta and allow caption processing before creating these notes.')
        try:identifier=video_id(body.url)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if body.end_seconds is not None and body.end_seconds<=body.start_seconds:
            raise HTTPException(422,'The end time must be after the start time.')
        if who in busy:
            raise HTTPException(409,'This browser is already creating lesson notes.')
        busy.add(who)
        try:
            if body.caption_text.strip():
                if not body.caption_reviewed:
                    raise HTTPException(409,'Review the pasted captions first.')
                chunks=[{'id':f'video-{identifier}-manual','start':None,'end':None,'text':body.caption_text.strip()}]
                source='Learner-supplied captions; timing and completeness unverified'
                language='as supplied';generated=None
            else:
                try:
                    record=await asyncio.wait_for(asyncio.to_thread(fetch_captions,identifier,cache),35)
                    chunks=source_chunks(identifier,record,body.start_seconds,body.end_seconds)
                except ValueError as error:
                    raise HTTPException(422,str(error)) from None
                except Exception:
                    raise HTTPException(503,'YouTube captions could not be retrieved. Try later or paste captions under More options. No model request was made.') from None
                source=record['origin'];language=record['language'];generated=record['is_generated']
            evidence={'caption_source':source,'auto_generated':generated,'caption_chunks':chunks}
            if len(json.dumps(evidence))>24000:
                raise HTTPException(422,'Choose a shorter time range for this pilot. No model request was made.')
            reserve_cloud(who,True,'YouTube caption study notes')
            try:
                result=await meta.generate('Write readable, original teaching notes for a Python beginner, about 350-500 words and under 5500 characters including citations. Use Markdown: short ## section headings, blank lines, short paragraphs with one main idea, bullets where useful, backticks for Python terms, and fenced python blocks for code. Start with what the learner will understand and explain any prerequisites. Teach the important concepts in the selected captions in a sensible order, explaining why each operation is useful. Include one small original worked example labelled Added practice, state its expected output and walk through the key lines; this is an explanatory prediction, not an executed result. Include common mistakes and two short self-check questions. Cite supplied source IDs beside the explanation they support. Label added examples and questions as original practice rather than observed video content. Correct obvious speech-recognition errors only when the intended programming term is clear. Do not reproduce the transcript, invent missing lesson sections, claim to see slides or images, claim code was executed, or certify mastery. Use Python terminology such as None rather than JSON null.',evidence,[c['id'] for c in chunks])
            except MetaUnavailable as error:
                raise HTTPException(503,str(error)) from None
            if any(identifier not in {c['id'] for c in chunks} for identifier in re.findall(r'\[(video-[A-Za-z0-9_-]+)\]',result['answer'])):
                raise HTTPException(503,'The notes contained an unknown caption reference. They were not saved.')
            title,topic=VIDEO_PRACTICE.get(identifier,('YouTube lesson',None))
            saved={**result,'video_id':identifier,'url':'https://www.youtube.com/watch?v='+identifier,'title':title,'caption_source':source,'language':language,'auto_generated':generated,'caption_chunks':chunks,'created':time.time(),'coverage':'Notes from available captions in the selected range. Video images were not analysed.','practice_topic':topic,'practice_basis':'Related original practice from the reviewed LessonTrace bank. These exercises were authored separately; they do not cover every part of this video.' if topic else 'Choose a related unit from the original practice bank. New exercises were not generated from this video.'}
            store.set_progress(who,'youtube_session',saved)
            return {'session':public_session(saved),'allowance':store.provider_allowance()}
        finally:
            busy.discard(who)
