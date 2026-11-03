"""Bounded, cached reads of the Loops pilot's curated public sources."""
from __future__ import annotations

import asyncio
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import uuid
from urllib.parse import quote, urlsplit

import httpx


CATALOG = {
    'cs50-loops': {
        'id':'cs50-loops', 'title':'CS50P · Loops', 'kind':'video',
        'url':'https://www.youtube.com/watch?v=-7xg8pGcP6w',
        'fetch_url':'https://cdn.cs50.net/python/2022/x/lectures/2/lang/en/lecture2.srt',
        'description':'Creator-published timed captions: while, for, range, lists, loop control and nested examples.',
    },
    'python-control-flow': {
        'id':'python-control-flow', 'title':'Python · Official control-flow reference', 'kind':'web',
        'url':'https://docs.python.org/3/tutorial/controlflow.html',
        'fetch_url':'https://docs.python.org/3/tutorial/controlflow.html',
        'description':'Primary Python 3 reference for iteration, range, break, continue and loop else.',
    },
    'learnpython-loops': {
        'id':'learnpython-loops', 'title':'LearnPython · Loops', 'kind':'web',
        'url':'https://www.learnpython.org/en/Loops',
        'fetch_url':'https://www.learnpython.org/en/Loops',
        'description':'An alternative explanation; inspect the version context of its range/xrange discussion.',
    },
}
FOCUS = {
    'foundations':['for','while','condition','iteration','repeat','range'],
    'nested-break':['nested','inner','outer','break','else','continue'],
    'range-iteration':['range','xrange','index','indices','iterable','list'],
}
MAX_BYTES=600_000


def catalog():
    return [{k:v for k,v in item.items() if k!='fetch_url'} for item in CATALOG.values()]


class Sections(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections=[];self.parts=[];self.heading='Introduction';self.anchor=''
        self.pending_anchor='';self.in_heading=False;self.heading_parts=[];self.pre=False;self.skip=[]

    def flush(self):
        text=''.join(self.parts).strip()
        if len(text)>=45:self.sections.append({'heading':self.heading,'anchor':self.anchor,'text':text})
        self.parts=[]

    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes)
        if tag in {'script','style','nav','footer','header','aside','form'}:
            self.skip.append(tag);return
        if self.skip:return
        if tag=='section' and attrs.get('id'):self.pending_anchor=attrs['id']
        if tag in {'h1','h2','h3','h4'}:
            self.flush();self.in_heading=True;self.heading_parts=[];self.anchor=attrs.get('id') or self.pending_anchor
        elif tag=='pre':self.pre=True;self.parts.append('\n')
        elif tag in {'p','li','div','br'}:self.parts.append('\n')

    def handle_endtag(self,tag):
        if self.skip:
            if tag==self.skip[-1]:self.skip.pop()
            return
        if tag in {'h1','h2','h3','h4'} and self.in_heading:
            self.heading=''.join(self.heading_parts).strip().replace('¶','');self.in_heading=False
        elif tag=='pre':self.pre=False;self.parts.append('\n')
        elif tag in {'p','li','div'}:self.parts.append('\n')

    def handle_data(self,data):
        if self.skip:return
        if self.in_heading:self.heading_parts.append(data)
        else:self.parts.append(data if self.pre else re.sub(r'\s+',' ',data))


def srt_sections(text):
    groups={};current=None;words=[];lines=text.replace('\r','').splitlines()
    def flush():
        if current and words:
            start,end=current;bucket=int(start//120)
            group=groups.setdefault(bucket,{'heading':'CS50 lecture excerpt','start':start,'end':end,'parts':[]})
            group['end']=end;group['parts'].append(' '.join(words))
    def seconds(value):
        h,m,s=value.replace(',','.').split(':');return int(h)*3600+int(m)*60+float(s)
    for i,line in enumerate(lines):
        match=re.fullmatch(r'(\d\d:\d\d:\d\d[,\.]\d+)\s*-->\s*(\d\d:\d\d:\d\d[,\.]\d+).*',line.strip())
        if match:
            flush();current=(seconds(match[1]),seconds(match[2]));words=[]
        elif line.strip().isdigit() and i+1<len(lines) and '-->' in lines[i+1]:continue
        elif line.strip():words.append(re.sub(r'<[^>]*>','',line.strip()))
    flush()
    return [dict(g,text=' '.join(g['parts'])) for g in groups.values() if g['parts']]


def excerpts(identifier,text,focus,goal,catalogue=None,selection=None):
    item=(catalogue or CATALOG)[identifier]
    if item['kind']=='video':sections=srt_sections(text)
    else:
        parser=Sections();parser.feed(text);parser.flush();sections=parser.sections
    if selection:
        if item['kind']=='video':
            low,high=selection['window'];sections=[part for part in sections if low<=part['start']<high]
        else:
            normal=lambda value:re.sub(r'[^a-z0-9 ]','',value.lower())
            sections=[part for part in sections if any(normal(term) in normal(part['heading']) for term in selection['sections'])]
            expanded=[]
            for part in sections:
                offsets=next((offsets for heading,offsets in selection.get('text_windows',{}).items() if normal(heading) in normal(part['heading'])),[0])
                for offset in offsets:
                    if offset<len(part['text']):expanded.append(dict(part,text=part['text'][offset:offset+2700],source_offset=offset,excerpted=len(part['text'])>2700))
            sections=expanded
    if not sections:raise ValueError('No readable source sections were found for this concept.')
    terms=set(FOCUS.get(focus,[]))|set(re.findall(r'[a-z]{4,}',goal.lower()))-{'this','that','with','from','what','does','want','understand','python','have','about'}
    def score(pair):
        _,part=pair;heading=part['heading'].lower();body=part['text'].lower()
        return sum((6 if word in heading else 0)+min(4,len(re.findall(r'\b'+re.escape(word)+r'\b',body))) for word in terms)
    ranked=sorted(enumerate(sections),key=score,reverse=True)
    selected=sorted(ranked[:2],key=lambda pair:pair[0]);chunks=[]
    for index,part in selected:
        start=part.get('start');url=item['url']
        if start is not None:url+='&t='+str(int(start))
        elif part.get('anchor'):url+='#'+quote(part['anchor'],safe='-_.')
        chunks.append({'id':f'hub-{identifier}-{index+1:04d}','source_id':identifier,'source_title':item['title'],
            'kind':item['kind'],'url':url,'start':start,'end':part.get('end'),'heading':part['heading'],
            'text':part['text'][:2700],'truncated':part.get('excerpted',False) or len(part['text'])>2700,'source_offset':part.get('source_offset',0)})
    return chunks,len(sections)


class HubSourceLoader:
    def __init__(self,cache:Path,transport=None,catalogue=None,selections=None):
        self.cache=cache;self.transport=transport;self.catalogue=catalogue or CATALOG;self.selections=selections or {}

    async def read(self,identifier,focus,goal):
        catalogue=self.catalogue
        if identifier not in catalogue:raise ValueError('Choose a source from this Hub’s catalog.')
        self.cache.mkdir(parents=True,exist_ok=True)
        cached=self.cache/(identifier+'.json');data=None
        if cached.is_file():
            try:
                candidate=json.loads(cached.read_text(encoding='utf-8'))
                if time.time()-candidate['fetched_at']<86400 and candidate['fetch_url']==catalogue[identifier]['fetch_url'] and len(candidate['text'].encode())<=MAX_BYTES:
                    data=candidate
            except (OSError,ValueError,KeyError,TypeError):pass
        if data is None:
            url=catalogue[identifier]['fetch_url']
            async with httpx.AsyncClient(timeout=15,follow_redirects=False,transport=self.transport,trust_env=False) as client:
                for redirect in range(3):
                    async with client.stream('GET',url,headers={'Accept':'text/html,text/plain','User-Agent':'LessonTrace/0.1 (learning source reader)'}) as response:
                        if response.status_code in {301,302,303,307,308}:
                            target=str(response.url.join(response.headers.get('location','')));parts=urlsplit(target)
                            if parts.scheme!='https' or parts.hostname!=urlsplit(catalogue[identifier]['fetch_url']).hostname or parts.username or parts.password or parts.port not in {None,443}:
                                raise ValueError('The source redirected outside its approved public site.')
                            url=target;continue
                        if response.status_code!=200:raise ValueError('This source could not be read (HTTP '+str(response.status_code)+').')
                        content_type=response.headers.get('content-type','').lower()
                        if not any(kind in content_type for kind in ('text/html','text/plain','application/x-subrip','application/octet-stream')):
                            raise ValueError('The source returned an unsupported document type.')
                        body=bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body)>MAX_BYTES:raise ValueError('This source exceeds the pilot reading limit.')
                        text=bytes(body).decode('utf-8-sig',errors='replace')
                        data={'text':text,'fetch_url':catalogue[identifier]['fetch_url'],'fetched_at':time.time()}
                        temporary=cached.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                        try:
                            temporary.write_text(json.dumps(data),encoding='utf-8');temporary.replace(cached)
                        finally:temporary.unlink(missing_ok=True)
                        break
                else:raise ValueError('The source redirected too many times.')
        chunks,total=excerpts(identifier,data['text'],focus,goal,catalogue,self.selections.get(focus))
        return {'id':identifier,'title':catalogue[identifier]['title'],'kind':catalogue[identifier]['kind'],'url':catalogue[identifier]['url'],
            'fetched_at':data['fetched_at'],'content_hash':hashlib.sha256(data['text'].encode()).hexdigest(),
            'reviewed_sections':len(chunks),'available_sections':total,'coverage':'Selected relevant excerpts only; not a complete-source review.',
            'chunks':chunks}


async def read_safely(loader,identifier,focus,goal):
    try:return await asyncio.wait_for(loader.read(identifier,focus,goal),22)
    except asyncio.CancelledError:raise
    except Exception as error:
        message=str(error) if isinstance(error,ValueError) else 'The public source could not be reached.'
        return {'id':identifier,'title':CATALOG[identifier]['title'],'kind':CATALOG[identifier]['kind'],'url':CATALOG[identifier]['url'],'error':message[:220]}
