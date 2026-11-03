"""One course, five units, and a concept graph independent of unit completion."""
import hashlib
import json
VERSION='python-fundamentals-v2'
COURSE={'id':'python-fundamentals','title':'Python Fundamentals','version':VERSION}
UNITS=[
    ('fundamentals','Programming fundamentals with Python',['variables','arithmetic','strings','comparisons']),
    ('data-structures','Introduction to simple data structures',['lists','indexing','list_mutation','dictionaries','nested_data']),
    ('control-structures','Mastering control structures in Python',['if_else','boolean_logic']),
    ('loops','Exploring iterations of loops in Python',['for_loop','range','while_loop','loop_lists','loop_if_else','break','continue','nested_loops','inner_break']),
    ('functions','Defining and utilizing functions in Python',['functions','parameters','scope','functions_data'])]
_DEFS={
    'variables':('Values, names and output',[]),
    'arithmetic':('Arithmetic and changing values',['variables']),
    'strings':('Strings, quotes and length',['variables','arithmetic']),
    'comparisons':('Booleans and comparisons',['variables']),
    'lists':('Lists and their values',['variables']),
    'indexing':('Zero-based list indexing',['lists']),
    'list_mutation':('Updating, copying and sharing lists',['lists']),
    'dictionaries':('Dictionary keys and defaults',['variables','strings','indexing']),
    'nested_data':('Nested collections and tuples',['lists','indexing','dictionaries']),
    'if_else':('Choosing with if and else',['variables','comparisons']),
    'boolean_logic':('Combining conditions',['if_else']),
    'for_loop':('One item at a time: for loops',['variables','arithmetic','strings','lists','list_mutation']),
    'range':('Range and its excluded boundary',['for_loop','arithmetic','indexing']),
    'while_loop':('While loops and changing state',['variables','arithmetic','comparisons']),
    'loop_lists':('Processing lists with a loop',['for_loop']),
    'loop_if_else':('Choosing inside a loop',['for_loop','if_else']),
    'break':('Stopping the nearest loop',['for_loop','if_else']),
    'continue':('Skipping one iteration',['for_loop','if_else']),
    'nested_loops':('Outer and inner iterations',['for_loop','lists']),
    'inner_break':('A break inside nested loops',['nested_loops','break']),
    'functions':('Defining functions with an input and return',['variables','arithmetic']),
    'parameters':('Multiple and default arguments',['functions']),
    'scope':('Local names and call frames',['parameters']),
    'functions_data':('Functions over collections',['parameters','for_loop','lists'])}
TOPICS={};ORDER=[]
for unit_index,(unit_id,unit_title,identifiers) in enumerate(UNITS):
    for index,identifier in enumerate(identifiers):
        title,needs=_DEFS[identifier]
        TOPICS[identifier]={'id':identifier,'title':title,'unit_id':unit_id,'unit_title':unit_title,'unit_index':unit_index,'index':index,
            'needs':needs,'targets':[identifier],'pilot':unit_id=='loops','practice_kind':'function' if unit_id=='functions' else 'program'}
        ORDER.append(identifier)


def topic(identifier):
    if identifier not in TOPICS:raise ValueError('Choose a concept from the Python Fundamentals course.')
    return TOPICS[identifier]


def closure(identifiers):
    result=set();visiting=set()
    def visit(identifier):
        if identifier in visiting:raise ValueError('A concept prerequisite cycle is not allowed.')
        if identifier in result:return
        visiting.add(identifier)
        for dependency in topic(identifier)['needs']:visit(dependency)
        visiting.remove(identifier);result.add(identifier)
    for identifier in identifiers:visit(identifier)
    return result


def allowed_concepts(identifier):return closure([identifier])


def outline():
    return [{'id':identifier,'title':title,'number':index+1,'pilot':identifier=='loops','topics':[topic(t) for t in topics]} for index,(identifier,title,topics) in enumerate(UNITS)]


def graph_digest():return hashlib.sha256(json.dumps(outline(),sort_keys=True,separators=(',',':')).encode()).hexdigest()


closure(TOPICS)
