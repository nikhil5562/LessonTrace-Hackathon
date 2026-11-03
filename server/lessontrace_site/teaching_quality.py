"""Narrow, observable teaching-context checks, not a general semantic grader."""
from __future__ import annotations

import ast
import re


QUALITY_INSTRUCTION='''Make every explanation self-contained for a beginner. Before walking through concrete variable values, show the complete small program and its input/loop sequences in a fenced python block. Explain where the first values come from: for range, state the start, stop-excluded and step; for a list, show the list and which loop selects each item. Use one consistent worked example and its variable names, rather than suddenly switching to an unseen source example. A citation links evidence; it does not replace the example or its setup. Distinguish a loop variable, a list item and an index. Explain break precisely: control resumes immediately after the nearest enclosing loop, any remaining outer-body statements run, then the outer loop advances when its body ends. Do not claim it always jumps straight to the next outer value. Keep advanced for-else/factoring/prime examples out of a basic break explanation unless their complete code and prerequisites are taught. A quiz's code must illustrate the exact event and scope in its prompt, never serve as unrelated decoration. If the question says an inner break executes, show nested loops with an actual reached inner break. Use a small example distinct from the unfinished function exercise. Validation checks structure and execution, not every pedagogical claim.'''


def check_note_walkthrough(markdown):
    """A value-walk must refer to a name introduced by an earlier shown program.

    This intentionally targets concrete inline assignments after walkthrough cues.
    It neither interprets arbitrary prose nor proves a stated value is correct.
    """
    defined=set()
    fence=re.compile(r'(?ms)^[ \t]*```([^\n]*)\n(.*?)^[ \t]*```[ \t]*$')
    position=0
    def prose(text):
        for match in re.finditer(r'\b(?:for|when|with|then|next|at)\s+`\s*([A-Za-z_]\w*)\s*=(?!=)[^`]*`',text,re.I):
            if match[1] not in defined:
                raise ValueError('Explain where '+match[1]+' comes from before walking through its value. Show the complete small program, its input or loop sequence, and the variable definitions before that walkthrough. A source citation alone is not the setup.')
    for match in fence.finditer(markdown):
        prose(markdown[position:match.start()])
        try:tree=ast.parse(match[2]) if match[1].strip().casefold() in {'','python','py'} else None
        except SyntaxError:tree=None  # Existing code/example checks have separate responsibilities.
        if tree:
            defined.update(node.id for node in ast.walk(tree) if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Store))
        position=match.end()
    prose(markdown[position:])


def break_targets(source):
    """Break-line to lexical loop depth; a loop else is outside that loop body."""
    result={}
    def visit(node,depth):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda)):
            for child in ast.iter_child_nodes(node):visit(child,0)
        elif isinstance(node,(ast.For,ast.While,ast.AsyncFor)):
            for child in node.body:visit(child,depth+1)
            for child in node.orelse:visit(child,depth)
        else:
            if isinstance(node,ast.Break):result[node.lineno]=depth
            for child in ast.iter_child_nodes(node):visit(child,depth)
    visit(ast.parse(source),0)
    return result


def check_control_premise(question,source,observed):
    """Verify explicit positive claims that a break executes, including its scope."""
    prompt=question['prompt'].lower().replace('`','')
    # Keep hypothetical/absence questions and general no-code recall questions valid.
    claims_execution=bool(re.search(r'\bbreak\s+(?:runs?|executes?|is\s+(?:executed|reached))\b|\b(?:executes?|reaches?|hits?)\s+(?:an?\s+|the\s+)?break\b',prompt))
    if not claims_execution:return None
    if not source.strip():raise ValueError('The quiz says break executes. Show a complete runnable example containing that break, not an empty or unrelated code premise.')
    targets=break_targets(source)
    claims_inner=bool(re.search(r'\bbreak\b.{0,65}\b(?:inside|within|in)\s+(?:the\s+|an?\s+)?(?:inner|innermost)\s+loop\b|\b(?:inner|innermost)\s+loop\b.{0,40}\b(?:executes?|reaches?|hits?)\s+(?:an?\s+|the\s+)?break\b',prompt))
    eligible={line:depth for line,depth in targets.items() if depth>=(2 if claims_inner else 1)}
    if not eligible:
        raise ValueError('The quiz premise does not match its code. Show a break inside nested loops for an inner-break question; a single range loop or an outer break cannot illustrate that event.')
    executed={event['line'] for event in observed.get('events',[]) if event.get('control',{}).get('action')=='break'}
    matched=set(eligible)&executed
    if not matched:raise ValueError('The quiz says break executes, but Python did not reach the stated break. Supply an example whose actual execution matches that premise.')
    return {'control':'break','executed':True,'loop_depth':max(eligible[line] for line in matched)}
