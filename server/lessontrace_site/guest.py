"""Trusted trace harness. Run this file INSIDE the WASI guest, never host-exec user code."""

import ast
import hashlib
import io
import json
import math
import sys

FILENAME = "<lessontrace>"
MAX_EVENTS = 350
MAX_LINES = 1500


class Unsupported(ValueError):
    pass


class LimitReached(RuntimeError):
    pass


def validate(source, entry):
    if not isinstance(source, str) or len(source) > 8000:
        raise Unsupported("Keep the program under 8,000 characters.")
    tree = ast.parse(source, filename=FILENAME)
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign, ast.AugAssign,
               ast.Expr, ast.Return, ast.For, ast.While, ast.If, ast.Break, ast.Continue,
               ast.Pass, ast.Name, ast.Load, ast.Store, ast.Constant, ast.List, ast.Tuple,
               ast.Call, ast.Attribute, ast.Compare, ast.Gt, ast.GtE, ast.Lt, ast.LtE,
               ast.Eq, ast.NotEq, ast.Is, ast.IsNot, ast.In, ast.NotIn, ast.BinOp,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.UnaryOp,
               ast.USub, ast.UAdd, ast.Not, ast.BoolOp, ast.And, ast.Or, ast.Subscript,
               ast.keyword, ast.Dict, ast.JoinedStr, ast.FormattedValue)
    nodes = list(ast.walk(tree))
    if len(nodes) > 500:
        raise Unsupported("This example is too large for the pilot runner.")
    functions = {n.name for n in nodes if isinstance(n, ast.FunctionDef)}
    for node in nodes:
        if not isinstance(node, allowed):
            raise Unsupported(type(node).__name__ + " is outside this lesson's supported Python subset.")
        if isinstance(node, (ast.Name, ast.arg)):
            name = node.id if isinstance(node, ast.Name) else node.arg
            if name.startswith("_"):
                raise Unsupported("Private and interpreter names are outside this lesson.")
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and name in {"print", "len", "range", "sum"}:
                raise Unsupported("Do not replace a built-in function in this lesson.")
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("_") or node.name in {"print", "len", "range"} or node.decorator_list or node.returns or node.type_comment:
                raise Unsupported("Use ordinary lesson functions without decorators or annotations.")
            if any(not isinstance(default,ast.Constant) for default in node.args.defaults) or node.args.kw_defaults or node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.posonlyargs:
                raise Unsupported("Use simple positional parameters and scalar literal defaults in this lesson.")
        if isinstance(node, ast.arg) and node.annotation:
            raise Unsupported("Type annotations are outside this pilot.")
        if isinstance(node, ast.Attribute) and node.attr not in {"append", "copy", "items", "keys", "values", "get", "pop", "popitem"}:
            raise Unsupported("Use the supported list or dictionary methods: append, copy, items, keys, values, get, pop and popitem.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in functions | {"print", "len", "range", "sum"}:
            raise Unsupported("This function is not available in the pilot runner.")
        if isinstance(node, ast.Call) and not isinstance(node.func, (ast.Name, ast.Attribute)):
            raise Unsupported("Use direct calls to the supported functions.")
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))) or isinstance(node.value, str) and len(node.value) > 500:
                raise Unsupported("Use short strings and ordinary numeric values.")
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and abs(node.value) > 1_000_000:
                raise Unsupported("Use numeric literals no larger than one million.")
    if entry and (entry not in functions or any(not isinstance(n, ast.FunctionDef) for n in tree.body)):
        raise Unsupported("Define the requested function; keep top-level example calls out of your attempt.")
    return tree


class Instrument(ast.NodeTransformer):
    def __init__(self):
        self.loop_stack = []

    def visit_For(self, node):
        self.loop_stack.append(node.lineno)
        self.generic_visit(node)
        self.loop_stack.pop()
        target = ast.unparse(node.target)
        node.iter = ast.copy_location(ast.Call(func=ast.Name(id="_lt_iter", ctx=ast.Load()), args=[ast.Constant(node.lineno), node.iter, ast.Constant(target)], keywords=[]), node.iter)
        return node

    def visit_If(self, node):
        self.generic_visit(node)
        node.test = ast.copy_location(ast.Call(func=ast.Name(id="_lt_condition", ctx=ast.Load()), args=[ast.Constant(node.lineno), node.test], keywords=[]), node.test)
        return node

    def visit_While(self, node):
        self.loop_stack.append(node.lineno)
        result = self.visit_If(node)
        self.loop_stack.pop()
        return result

    def visit_Break(self, node):
        return self.control(node, "break")

    def visit_Continue(self, node):
        return self.control(node, "continue")

    def control(self, node, action):
        notice = ast.Expr(value=ast.Call(func=ast.Name(id="_lt_control", ctx=ast.Load()), args=[ast.Constant(node.lineno), ast.Constant(action), ast.Constant(self.loop_stack[-1])], keywords=[]))
        return [ast.copy_location(notice, node), node]


class Collector:
    def __init__(self, capture):
        self.capture = capture
        self.events = []
        self.pending = {}
        self.stack = []
        self.frame_ids = {}
        self.kept_frames = {}
        self.kept_objects = {}
        self.conditions = {}
        self.loops = {}
        self.controls = {}
        self.lines = 0
        self.output = ""

    def print(self, *values, sep=" ", end="\n"):
        if not isinstance(sep, str) or not isinstance(end, str):
            raise ValueError("print separators must be strings")
        text = sep.join(str(v) for v in values) + end
        if len(self.output) + len(text) > 4096:
            raise LimitReached("Printed output limit reached.")
        self.output += text

    def condition(self, line, value):
        frame = sys._getframe(1)
        self.conditions[(id(frame), line)] = bool(value)
        return value

    def control(self, line, action, loop_line):
        frame_id = id(sys._getframe(1))
        self.controls[(frame_id, line)] = {"action": action, "loop_line": loop_line}
        if action == "break" and (frame_id, loop_line) in self.loops:
            self.loops[(frame_id, loop_line)]["broken"] = True

    def iterate(self, line, values, target):
        frame_id = id(sys._getframe(1))
        if not isinstance(values, (list, tuple, dict, str, range, type({}.items()), type({}.keys()), type({}.values()))):
            raise Unsupported("Iterate over a supported collection or bounded range.")
        if len(values) > 1000:
            raise LimitReached("Iteration limit reached.")
        iterable = self.value(values if not isinstance(values, range) else list(values), {})
        iterable_id = iterable.get("object_id")
        for index, value in enumerate(values):
            self.loops[(frame_id, line)] = {"line": line, "index": index, "target": target, "length": len(values), "exhausted": False, "iterable_id": iterable_id}
            yield value
        self.loops[(frame_id, line)] = {"line": line, "index": len(values), "target": target, "length": len(values), "exhausted": True, "iterable_id": iterable_id}

    def value(self, value, objects, depth=0):
        if value is None or isinstance(value, (bool, str, int, float)):
            if isinstance(value, str) and len(value) > 500 or isinstance(value, int) and value.bit_length() > 256 or isinstance(value, float) and not math.isfinite(value):
                raise LimitReached("Value size limit reached.")
            return {"kind": "scalar", "value": value}
        if isinstance(value, (list, tuple, dict, type({}.items()), type({}.keys()), type({}.values()))):
            if len(value) > 128 or depth > 8:
                raise LimitReached("List size or nesting limit reached.")
            identity = id(value)
            if identity not in self.kept_objects:
                if len(self.kept_objects) >= 128:
                    raise LimitReached("Object limit reached.")
                self.kept_objects[identity] = (value, "o" + str(len(self.kept_objects) + 1))
            oid = self.kept_objects[identity][1]
            if oid not in objects:
                objects[oid] = {"type": type(value).__name__, "items": []}
                if isinstance(value, dict) or isinstance(value, type({}.items())):
                    pairs = value.items() if isinstance(value, dict) else value
                    objects[oid]["entries"] = [{"key": self.value(k, objects, depth + 1), "value": self.value(v, objects, depth + 1)} for k, v in pairs]
                else:
                    objects[oid]["items"] = [self.value(item, objects, depth + 1) for item in value]
            return {"kind": "reference", "object_id": oid}
        if callable(value):
            return {"kind": "function", "name": getattr(value, "__name__", "function")}
        raise Unsupported("The returned value is outside this lesson's supported types.")

    def emit(self, frame, line, kind="line", returned=None):
        objects = {}
        frames = []
        for active in self.stack:
            self.kept_frames[id(active)] = active
            if len(self.kept_frames) > 128:
                raise LimitReached("Function invocation limit reached.")
            fid = self.frame_ids.setdefault(id(active), "f" + str(len(self.frame_ids) + 1))
            bindings = {name: self.value(value, objects) for name, value in active.f_locals.items() if not name.startswith("_")}
            frames.append({"id": fid, "name": active.f_code.co_name, "bindings": bindings})
        result = self.value(returned, objects) if kind == "return" else None
        for (fid, _), loop in self.loops.items():
            if fid == id(frame) and loop.get("iterable_id"):
                held = next((item for item in self.kept_objects.values() if item[1] == loop["iterable_id"]), None)
                if held:
                    self.value(held[0], objects)
        if not self.capture:
            return
        if len(self.events) >= MAX_EVENTS:
            raise LimitReached("Trace limit reached; shorten the example.")
        event = {"step": len(self.events), "line": line, "kind": kind, "frames": frames, "objects": objects, "output": self.output,
                 "loops": [dict(position) for (fid, _), position in self.loops.items() if fid == id(frame)]}
        condition = self.conditions.get((id(frame), line))
        if condition is not None:
            event["condition"] = condition
        if (id(frame), line) in self.controls:
            event["control"] = self.controls[(id(frame), line)]
        if kind == "return":
            event["returned_value"] = result
        self.events.append(event)

    def trace(self, frame, event, arg):
        if frame.f_code.co_filename != FILENAME:
            return self.trace
        key = id(frame)
        if event == "call":
            if len(self.stack) > 15:
                raise LimitReached("Function-call depth limit reached.")
            self.stack.append(frame)
        elif event == "line":
            self.lines += 1
            if self.lines > MAX_LINES:
                raise LimitReached("Execution step limit reached.")
            if key in self.pending:
                self.emit(frame, self.pending[key])
            self.pending[key] = frame.f_lineno
        elif event in {"return", "exception"}:
            if key in self.pending:
                line = self.pending.pop(key)
                self.emit(frame, line, "return" if event == "return" else "exception", arg if event == "return" else None)
                if event == "exception" and self.capture:
                    self.events[-1]["error"] = {"type": arg[0].__name__, "message": str(arg[1])[:300]}
            if event == "return" and frame in self.stack:
                self.stack.remove(frame)
        return self.trace


def run_case(source, tree, entry, arguments, capture, program_inputs=None, result_name=None):
    collector = Collector(capture)
    builtins = {"print": collector.print, "len": len, "range": range, "sum": sum}
    namespace = {"__builtins__": builtins, "_lt_condition": collector.condition, "_lt_iter": collector.iterate, "_lt_control": collector.control}
    if program_inputs is not None:namespace.update(zip(program_inputs,arguments))
    code = compile(ast.fix_missing_locations(Instrument().visit(tree)), FILENAME, "exec")
    result = None
    failure = None
    try:
        if entry:
            exec(code, namespace)
            sys.settrace(collector.trace)
            result = namespace[entry](*arguments)
        else:
            sys.settrace(collector.trace)
            exec(code, namespace)
            if program_inputs is not None:
                if result_name not in namespace:raise NameError('Assign the requested result variable '+result_name+'.')
                result=namespace[result_name]
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)[:300]}
    finally:
        sys.settrace(None)
        collector.stack.clear()
    if failure:
        return {"error": failure, "output": collector.output, "events": collector.events}
    objects = {}
    serial = collector.value(result, objects)
    # The host compares plain values against its independent expected results.
    def plain(value, seen=None):
        seen = set() if seen is None else seen
        if isinstance(value, (list, tuple, dict)):
            if id(value) in seen:
                raise Unsupported("Cyclic return values are outside the exercise contract.")
            if isinstance(value, dict):
                if any(not isinstance(k, str) for k in value):
                    raise Unsupported("Return dictionaries with string keys in this pilot.")
                return {k: plain(v, seen | {id(value)}) for k, v in value.items()}
            return [plain(v, seen | {id(value)}) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise Unsupported("Return an ordinary value, not a function.")
    return {"actual": plain(result), "arguments_after": plain(arguments), "return_type": type(result).__name__, "returned_value": serial, "output": collector.output, "events": collector.events}


def main(payload):
    source = payload["source"]
    entry = payload.get("entry")
    program_inputs=payload.get('program_inputs');result_name=payload.get('result_name')
    if program_inputs is not None:
        reserved={'print','len','range','sum'}
        names=program_inputs+[result_name] if isinstance(program_inputs,list) and isinstance(result_name,str) else []
        if entry or not names or len(program_inputs)>4 or len(set(names))!=len(names) or any(not isinstance(n,str) or not n.isidentifier() or n.startswith('_') or n in reserved for n in names):
            raise Unsupported('Use distinct ordinary input and result names for program practice.')
    validate(source, entry)
    cases = payload.get("arguments", [[]])
    if len(cases) > 10:
        raise Unsupported("Too many test cases.")
    results = []
    for index, arguments in enumerate(cases):
        if program_inputs is not None and len(arguments)!=len(program_inputs):raise Unsupported('Program inputs do not match this check.')
        # Parse separately because instrumentation mutates the AST.
        results.append(run_case(source, validate(source, entry), entry, arguments, index == payload.get("trace_case", 0),program_inputs,result_name))
    return {"schema_version": 1, "runtime": "CPython " + sys.version.split()[0] + " / WASI", "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "cases": results}


if __name__ == "__main__":
    try:
        result = main(json.loads(sys.stdin.read(40000)))
    except BaseException as error:
        result = {"error": {"type": type(error).__name__, "message": str(error)[:300]}}
    print(json.dumps(result, allow_nan=False, separators=(",", ":")))
