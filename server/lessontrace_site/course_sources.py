"""Same bounded source reader, restricted to topic sections and creator captions."""
from .hub_sources import HubSourceLoader,CATALOG

SOURCES={
    'python-control-flow':CATALOG['python-control-flow'],
    'cs50-loops':CATALOG['cs50-loops'],
    'learnpython-loops':CATALOG['learnpython-loops'],
    'python-introduction':{'id':'python-introduction','title':'Python · Introduction','kind':'web','url':'https://docs.python.org/3/tutorial/introduction.html','fetch_url':'https://docs.python.org/3/tutorial/introduction.html'},
    'python-data-structures':{'id':'python-data-structures','title':'Python · Data structures','kind':'web','url':'https://docs.python.org/3/tutorial/datastructures.html','fetch_url':'https://docs.python.org/3/tutorial/datastructures.html'},
    'python-scopes':{'id':'python-scopes','title':'Python · Scopes and namespaces','kind':'web','url':'https://docs.python.org/3/tutorial/classes.html#python-scopes-and-namespaces','fetch_url':'https://docs.python.org/3/tutorial/classes.html'},
    'cs50-basics':{'id':'cs50-basics','title':'CS50P · Functions and variables','kind':'video','url':'https://www.youtube.com/watch?v=JP7ITIXGpHk','fetch_url':'https://cdn.cs50.net/python/2022/x/lectures/0/lang/en/lecture0.srt'},
    'cs50-conditionals':{'id':'cs50-conditionals','title':'CS50P · Conditionals','kind':'video','url':'https://www.youtube.com/watch?v=_b6NgY_pMdw','fetch_url':'https://cdn.cs50.net/python/2022/x/lectures/1/lang/en/lecture1.srt'}}
SELECTIONS={
    'variables':{'sections':['numbers'],'window':(840,1200)},
    'arithmetic':{'sections':['numbers'],'window':(3480,4320)},
    'strings':{'sections':['text'],'window':(1440,2640),'text_windows':{'text':[0,5000]}},
    'comparisons':{'sections':['if statements'],'window':(0,360)},
    'lists':{'sections':['lists'],'window':(2040,2280)},
    'indexing':{'sections':['lists'],'window':(2160,2400)},
    'list_mutation':{'sections':['more on lists'],'window':(2040,2400)},
    'dictionaries':{'sections':['dictionaries'],'window':(2760,3240)},
    'nested_data':{'sections':['tuples and sequences','dictionaries'],'window':(3360,3840)},
    'if_else':{'sections':['if statements'],'window':(120,960)},
    'boolean_logic':{'sections':['more on conditions'],'window':(1080,1920)},
    'functions':{'sections':['defining functions'],'window':(5400,6337),'text_windows':{'defining functions':[0,1800]}},
    'parameters':{'sections':['default argument values'],'window':(5400,5760)},
    'scope':{'sections':['python scopes and namespaces'],'window':(5760,6120),'text_windows':{'python scopes and namespaces':[0,2600]}},
    'functions_data':{'sections':['defining functions','for statements'],'window':(1920,2280)},
    'for_loop':{'sections':['for statements','the range function','loops'],'window':(600,1700)},
    'range':{'sections':['the range function','loops'],'window':(600,1800)},
    'while_loop':{'sections':['first steps towards programming','loops'],'window':(0,900)},
    'loop_lists':{'sections':['for statements','loops'],'window':(900,2200)},
    'loop_if_else':{'sections':['for statements','break and continue','if statements','loops'],'window':(600,2600)},
    'break':{'sections':['break and continue','loops'],'window':(0,2600)},
    'continue':{'sections':['break and continue','loops'],'window':(0,2600)},
    'nested_loops':{'sections':['for statements','break and continue','loops'],'window':(4200,5600)},
    'inner_break':{'sections':['break and continue','loops'],'window':(4200,5600)}}


def loader(cache,transport=None):return HubSourceLoader(cache,transport,catalogue=SOURCES,selections=SELECTIONS)


def catalog_for(concept):
    # The pilot is bounded to a reviewed topic/source menu, never arbitrary URLs.
    groups={**dict.fromkeys(['variables','arithmetic','strings'],['python-introduction','cs50-basics']),
        **dict.fromkeys(['lists','indexing'],['python-introduction','cs50-loops']),
        **dict.fromkeys(['list_mutation','dictionaries','nested_data'],['python-data-structures','cs50-loops']),
        **dict.fromkeys(['comparisons','if_else'],['python-control-flow','cs50-conditionals']),
        'boolean_logic':['python-data-structures','cs50-conditionals'],
        **dict.fromkeys(['functions','parameters'],['python-control-flow','cs50-basics']),
        'scope':['python-scopes','cs50-basics'],'functions_data':['python-control-flow','cs50-loops']}
    ids=groups.get(concept,['python-introduction','cs50-loops','learnpython-loops'] if concept=='while_loop' else ['python-control-flow','cs50-loops','learnpython-loops'])
    return [{k:v for k,v in SOURCES[i].items() if k!='fetch_url'} for i in ids]
