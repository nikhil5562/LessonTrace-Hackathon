"""Prerequisite tags checked against constructs, not a semantic teaching proof."""
import ast
import re
from .course_catalog import topic,allowed_concepts,TOPICS


def inferred(source):
    tree=ast.parse(source);required={'variables'}
    for item in ast.walk(tree):
        if isinstance(item,ast.List):required.add('lists')
        if isinstance(item,ast.Dict):required.add('dictionaries')
        if isinstance(item,ast.Tuple):required.add('for_loop' if isinstance(item.ctx,ast.Store) else 'nested_data')
        if isinstance(item,ast.Subscript):required.add('indexing')
        if isinstance(item,(ast.BinOp,ast.AugAssign)):required.add('arithmetic')
        if isinstance(item,ast.Compare):required.add('comparisons')
        if isinstance(item,ast.BoolOp) or isinstance(item,ast.UnaryOp) and isinstance(item.op,ast.Not):required.add('boolean_logic')
        if isinstance(item,ast.If):required.add('if_else')
        if isinstance(item,ast.For):required.add('for_loop')
        if isinstance(item,ast.While):required.add('while_loop')
        if isinstance(item,ast.Break):required.add('break')
        if isinstance(item,ast.Continue):required.add('continue')
        if isinstance(item,(ast.FunctionDef,ast.Return)):required.add('functions')
        if isinstance(item,ast.FunctionDef) and (item.args.defaults or len(item.args.args)>1):required.add('parameters')
        if isinstance(item,(ast.JoinedStr,ast.FormattedValue)):raise ValueError('Use plain taught strings, not f-strings in this course version.')
        if isinstance(item,ast.Call):
            if isinstance(item.func,ast.Name):
                if item.func.id=='range':required.add('range')
                elif item.func.id=='len':required.add('strings')
                elif item.func.id!='print':required.add('functions')
            elif isinstance(item.func,ast.Attribute):
                name=item.func.attr
                if name in {'append','copy'}:required.add('list_mutation')
                elif name=='get':required.add('dictionaries')
                elif name in {'items','keys','values'}:required.update({'for_loop','dictionaries'})
                else:raise ValueError('This method has not been introduced in this course version: '+name+'.')
    return required


def check_code(source,topic_id):
    missing=inferred(source)-allowed_concepts(topic_id)
    if missing:raise ValueError('Untaught concept prerequisites: '+', '.join(sorted(missing))+'. Do not include these in this lesson.')


def code_blocks(text):
    for language,code in re.findall(r'^[ \t]*```([^\n]*)\n(.*?)^[ \t]*```[ \t]*$',text,re.S|re.M):
        language=language.strip().casefold()
        if language in {'python','py'}:yield code
        elif language not in {'text','output'}:raise ValueError('Label runnable code fences python and displayed output fences text. Do not leave their meaning ambiguous.')


def check_text(text,topic_id):
    for code in code_blocks(text):check_code(code,topic_id)


def tags(value,topic_id,sources=()):
    needs=value.get('needs');targets=value.get('targets')
    if not isinstance(needs,list) or not isinstance(targets,list) or not targets or set(needs+targets)-set(TOPICS):raise ValueError('Every course question and task needs known prerequisite and target concept tags.')
    if set(targets)!={topic_id}:raise ValueError('This question must target its current concept.')
    if set(needs)-(allowed_concepts(topic_id)-{topic_id}):raise ValueError('This question needs concepts outside the lesson prerequisites.')
    derived=set().union(*(inferred(source) for source in sources))-{topic_id} if sources else set()
    missing=derived-(allowed_concepts(topic_id)-{topic_id})
    if missing:raise ValueError('Code uses untaught '+', '.join(sorted(missing))+', regardless of declared tags. Remove those constructs from this lesson, including distractors and reference solutions.')
    # Labels proposed by the model cannot conceal a construct. Derive missing
    # safe prerequisites instead of spending a repair request on metadata alone.
    value['needs']=sorted(set(needs)|derived)


def eligible(value,demonstrated):return set(value.get('needs',[]))<=set(demonstrated)


def require_target(source,concept,exercise=None,trace=None):
    tree=ast.parse(source)
    def has_nested(node,depth=0):
        if isinstance(node,(ast.For,ast.While)):depth+=1
        return depth>=2 or any(has_nested(child,depth) for child in ast.iter_child_nodes(node))
    def inner_break(node,depth=0):
        if isinstance(node,(ast.For,ast.While)):depth+=1
        return isinstance(node,ast.Break) and depth>=2 or any(inner_break(child,depth) for child in ast.iter_child_nodes(node))
    checks={'for_loop':lambda:any(isinstance(n,ast.For) for n in ast.walk(tree)),
        'range':lambda:any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='range' for n in ast.walk(tree)),
        'while_loop':lambda:any(isinstance(n,ast.While) for n in ast.walk(tree)),
        'loop_lists':lambda:any(isinstance(n,ast.For) for n in ast.walk(tree)),
        'loop_if_else':lambda:any(isinstance(child,ast.If) for n in ast.walk(tree) if isinstance(n,(ast.For,ast.While)) for child in ast.walk(n)),
        'break':lambda:any(isinstance(n,ast.Break) for n in ast.walk(tree)),
        'continue':lambda:any(isinstance(n,ast.Continue) for n in ast.walk(tree)),
        'nested_loops':lambda:has_nested(tree),'inner_break':lambda:inner_break(tree)}
    if concept in checks and not checks[concept]():raise ValueError('This check must actually practise '+concept+', not bypass it with another operation.')
    if concept=='scope':
        helpers=set((exercise or {}).get('required_helpers',[]));definitions={n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
        calls={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        observed={frame['name'] for event in trace or [] for frame in event.get('frames',[])}
        if len(helpers)<2 or not helpers<=definitions&calls or trace is not None and not helpers<=observed:
            raise ValueError('Use the task’s two helper functions so their separate local call frames can be observed; equivalent arithmetic alone does not practise this objective.')


def check_exercise(exercise,topic_id):
    if exercise.get('kind','function')!=topic(topic_id)['practice_kind']:raise ValueError('Use the required practice format; do not introduce def/return before the functions unit.')
    for field in ('starter','reference_solution'):check_code(exercise[field],topic_id)
    check_text(exercise['instructions'],topic_id)


def check_lesson(lesson,topic_id):
    check_text(lesson['answer'],topic_id)
    for unit in lesson['units']:
        check_text(unit['explanation'],topic_id);check_exercise(unit['exercise'],topic_id);check_code(unit['prediction']['code'],topic_id)
        for question in unit['quiz']:
            if question['kind']=='complete_code':
                for option in question['options']:check_code(question['code'].replace('___',option),topic_id)
            elif question['code'].strip():check_code(question['code'],topic_id)
            check_text(question['explanation'],topic_id)


def instruction(topic_id):
    item=topic(topic_id)
    design={
        'variables':'Teach assignment, names, scalar values and print, including reassignment. Main/fresh programs use one supplied scalar input and assign it to a new result name. No operators, collections, len, branches or function definitions.',
        'arithmetic':'Teach numeric arithmetic and changing values using supplied numeric inputs. No len, collections, comparisons, branches, loops or function definitions.',
        'strings':'Teach quoted text, concatenation and len. No indexing, string methods, f-strings, collections, branches, loops or definitions. Use strings with supplied inputs.',
        'comparisons':'Teach numeric comparisons as True/False values without any if/else. No arithmetic operators, collections, len, loops or definitions.',
        'lists':'Teach list literals and grouping values. Build a list from supplied scalar inputs. No indexing, len, methods, loops, branches or definitions.',
        'indexing':'Teach zero-based non-negative indexing in a supplied nonempty list. No arithmetic, len, methods, loops, branches, dictionary literals or definitions.',
        'list_mutation':'Teach append, copy, mutation and aliasing. Main/fresh must copy a supplied list before appending to preserve it. No indexing, len, arithmetic, branches, loops or definitions.',
        'dictionaries':'Teach exact quoted keys, dictionary values, lookup and get defaults. No dictionary iteration or items/keys/values methods, comprehensions, loops, branches or definitions.',
        'nested_data':'Teach nested dictionaries/lists/tuples with complete setup and direct access. No tuple unpacking, loops, comprehensions, branches or definitions.',
        'if_else':'Teach if/else using numeric comparisons and simple literal outputs. No arithmetic, modulo, elif, boolean operators, collections, len, loops or definitions.',
        'boolean_logic':'Teach and/or/not combining numeric comparisons, with if/else if useful. No arithmetic, collections, len, loops or definitions.',
        'functions':'Teach def, one positional parameter/input name, calling and return together. Parameters ARE introduced here at a basic level; later lessons expand them. Main/fresh use kind function, exactly one scalar argument, and return a computed numeric value. No defaults, multiple arguments, len, collections, branches, loops or global declarations.',
        'parameters':'Expand the basic parameter idea to multiple/default scalar arguments and call order. Main/fresh kind function, short numeric arithmetic and distinct case arguments. No mutable defaults, keyword-only parameters, collections, branches, loops or globals.',
        'scope':'Explain local names and call frames using parameters and two simple helper functions. Set required_helpers to the two helper names for both exercises and explicitly state their unchanged calculations in each contract. Notes may demonstrate a module variable and a local name; assessed function source must contain only function definitions. No global/nonlocal declarations, closures, collections, branches or loops.',
        'functions_data':'Use kind function with one supplied list, for iteration and append to build and return a new list. No dictionary operations, indexing, if/else, while, range, break or continue.',
        'for_loop':'Transform or copy EVERY list item using for and append. Never filter with if, and do not use range, while or break yet.',
        'range':'Build a range-based sequence with for. No if, while, break or continue.',
        'while_loop':'Use SCALAR numeric inputs and a numeric result with while updates. No lists, for, range, if or break.',
        'loop_lists':'Process a supplied list with for and an index when needed. No conditions, range, while or break.',
        'loop_if_else':'Combine for over a list with if/else. No range, while, break or continue.',
        'break':'Scan a list with for, if and break. No nested loops, range, while or continue.',
        'continue':'Scan a list with for, if and continue. No break, range, while or nested loops.',
        'nested_loops':'Use two nested for loops over lists. No if, break, range, while or continue.',
        'inner_break':'Use nested for loops over lists, if and an INNER break, preserving outer progress. No range, while or continue.'}.get(topic_id,'')
    return ('Prerequisite-checked concept: '+item['title']+'. Task design: '+design+' Allowed concepts (prerequisites plus current target): '+', '.join(sorted(allowed_concepts(topic_id)))+
        '. Never borrow untaught constructs from later source sections, including notes, debugging distractors and practice. Builtin print is allowed; len requires the strings/length concept; range requires range; append/copy require list_mutation. No f-strings, imports, input, comprehensions or slices. Practice format: '+item['practice_kind']+
        '. Before the functions unit use a plain top-level program, not def/return. Each needs tag lists every prerequisite construct used by its code; targets contains only '+topic_id+
        '. Show complete setup before walking values. Fresh tasks state goals and inputs without implementation hints or a derived range expression. Checked attempts are not proof of durable mastery.')
