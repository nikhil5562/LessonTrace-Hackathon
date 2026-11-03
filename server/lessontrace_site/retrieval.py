"""Small English programming-query expansion and transparent lexical ranking."""
from __future__ import annotations

from collections import Counter
import math
import re

VERSION='programming-lexical-v1'
STOP={'the','and','with','this','that','what','why','does','from','have','there','when','would','should','could','please','help','expected','thought','want','wanted','my','me','it','is','are','was','not','can','you','but','how','after','before','then'}
ALIASES=[
    (r'\bboth\b.{0,35}\b(?:loops?|repeats?)\b|\b(?:inner|outer|nested)\b.{0,35}\b(?:stop|end|leave)',('break','nearest','enclosing','inner','outer','loop')),
    (r'off[ -]by[ -]one|last.{0,30}(?:missing|included|skipped|there)|one (?:less|short)|(?:upper|end) (?:number|value)',('range','stop','exclusive','endpoint')),
    (r'(?:change|changing|edit).{0,35}(?:both|other)|same (?:list|object)|points? to|shared',('alias','reference','shared','mutation','list')),
    (r'key.{0,25}(?:missing|found|error)|(?:capital|lowercase|uppercase|spelling)|not there',('dictionary','key','get','default','case')),
    (r'(?:first|third|second).{0,18}(?:item|element|position)|starts? (?:at|from) (?:one|zero)|number.{0,15}position',('list','index','zero','position')),
    (r'prints?.{0,20}none|returns? nothing|answer.{0,20}none',('function','return','print','none')),
    (r'forever|never.{0,18}(?:ends?|stops?)|keeps? repeating',('while','condition','update','termination')),
    (r'skip.{0,20}(?:item|rest)|next iteration',('continue','iteration','loop')),
]


def tokens(text):return [word for word in re.findall(r'[a-z][a-z0-9_]*',text.casefold()) if len(word)>1 and word not in STOP]


def terms(text):
    original=set(tokens(text));expanded=set()
    for pattern,words in ALIASES:
        if re.search(pattern,text,re.I):expanded.update(words)
    return original,expanded-original


def retrieve(chunks,text,preferred=(),limit=3):
    if not chunks:return []
    original,expanded=terms(text);documents=[Counter(tokens(chunk['text'])) for chunk in chunks]
    average=sum(sum(doc.values()) for doc in documents)/len(documents) or 1;preferred=set(preferred)
    frequencies={word:sum(word in doc for doc in documents) for word in original|expanded}
    def score(index):
        doc=documents[index];length=sum(doc.values());total=0
        for word in original|expanded:
            frequency=doc[word]
            if frequency:
                inverse=math.log(1+(len(documents)-frequencies[word]+.5)/(frequencies[word]+.5))
                total+=(1 if word in original else .45)*inverse*frequency/(frequency+1.2*(.25+.75*length/average))
        return total+.12*(chunks[index]['id'] in preferred),chunks[index]['id'] in preferred,-index
    return [chunks[index] for index in sorted(range(len(chunks)),key=score,reverse=True)[:limit]]
