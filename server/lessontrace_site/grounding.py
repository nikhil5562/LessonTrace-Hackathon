"""Exact source anchors. An anchor is not proof that a claim follows from it."""
from __future__ import annotations

import copy
import re


INSTRUCTION='''For every cited source ID, return evidence_quotes with source_id, claim and quote. claim is one short concept claim you are supporting, not an exercise answer or private reference solution. quote must be a short exact contiguous substring copied from that supplied passage, preserving its words, punctuation and whitespace, at most 180 characters and 25 words. Quote the relevant language rule, not the whole passage. Never invent a quote or cite an unread source. Code-execution observations have their own evidence; do not pretend a passage proves an observed output. Exact quote matching establishes the source of those words, not complete semantic support for every claim.'''


def schema(base,source_ids):
    result=copy.deepcopy(base)
    result.setdefault('properties',{})['evidence_quotes']={'type':'array','minItems':1,'maxItems':12,'items':{
        'type':'object','additionalProperties':False,'required':['source_id','claim','quote'],'properties':{
            'source_id':{'type':'string','enum':list(source_ids)},'claim':{'type':'string','minLength':8,'maxLength':240},
            'quote':{'type':'string','minLength':8,'maxLength':180}}}}
    result.setdefault('required',[]).append('evidence_quotes')
    return result


def cited_ids(value):
    result=set()
    if isinstance(value,dict):
        for key,item in value.items():
            if key in {'sources','evidence_ids'}:result.update(item)
            elif key=='source_id' and isinstance(item,str):result.add(item)
            elif key!='evidence_quotes':result.update(cited_ids(item))
    elif isinstance(value,list):
        for item in value:result.update(cited_ids(item))
    elif isinstance(value,str):result.update(re.findall(r'\[((?:video|hub)-[A-Za-z0-9_-]+)\]',value))
    return result


def verify(value,passages,required=None):
    quotes=value.get('evidence_quotes')
    if not isinstance(quotes,list) or not 1<=len(quotes)<=12:raise ValueError('Supply one exact evidence quote for every cited passage.')
    texts={part['id']:part['text'] for part in passages};accepted=[];covered=set()
    for entry in quotes:
        if not isinstance(entry,dict) or set(entry) not in ({'source_id','claim','quote'},{'source_id','claim','quote','quote_verified'}):raise ValueError('Each evidence quote needs source_id, claim and quote.')
        identifier,claim,quote=(entry[key] for key in ('source_id','claim','quote'))
        if not all(isinstance(item,str) for item in (identifier,claim,quote)) or not 8<=len(claim.strip())<=240 or not 8<=len(quote)<=180 or len(quote.split())>25:
            raise ValueError('Use a short source claim and an exact quote of at most 180 characters and 25 words.')
        if identifier not in texts or quote not in texts[identifier]:raise ValueError('The evidence quote does not match its supplied passage word for word. Correct the quote or remove that unsupported claim and citation.')
        accepted.append({'source_id':identifier,'claim':claim,'quote':quote,'quote_verified':True});covered.add(identifier)
    missing=(cited_ids(value) if required is None else set(required))-covered
    if missing:raise ValueError('Every cited source needs a matching exact quote; missing '+', '.join(sorted(missing))+'.')
    return accepted
