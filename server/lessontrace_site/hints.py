"""Deterministic, labelled help based only on an owned execution result."""
import ast


def local_hint(run, level):
    report = run.get("report") or {}
    checks = report.get("checks", [])
    failed = next((check for check in checks if not check["passed"]), None)
    if not failed:
        return {"text": "These checks passed. Explain why your state survives each iteration, then try the fresh task with less help.", "line": None, "basis": "Observed passing checks", "provider": "local"}
    source = run["source"]
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    comparison = next((n for n in ast.walk(tree) if isinstance(n, ast.Compare) and any(isinstance(op, ast.GtE) for op in n.ops)), None) if tree else None
    reset = None
    if tree:
        for loop in (n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))):
            for node in ast.walk(loop):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and node.value.value == 0:
                    reset = node
    line = None
    if comparison and any(not c["passed"] and c["input"] in ([20], ["Devika"]) for c in checks):
        failed = next(c for c in checks if not c["passed"] and c["input"] in ([20], ["Devika"]))
        texts = ["Should an item exactly at the threshold qualify? Inspect the comparison for the boundary case.", "Your rule says strictly greater. Explain what your current comparison does when the value equals the threshold.", "Compare the two decisions: greater than the threshold, and equal to it. Which one does the task permit?"]
        line = comparison.lineno
    elif reset:
        texts = ["Where does the program forget the progress from earlier iterations?", "Trace two qualifying items. Compare the remembered value before and after the start of the second iteration.", "The remembered state must survive the whole loop. Decide which setup belongs before repeated work begins."]
        line = reset.lineno
    elif failed.get("actual") is None and not failed.get("error"):
        texts = ["Look separately at what the function prints and what it returns. What does the caller receive?", "The task checks a returned value. Printing makes text visible, but does it send the answer back?", "Check whether every valid path, including empty input, reaches a return of the completed result."]
    elif failed.get("error"):
        texts = ["Read the observed error and its input. Identify the first operation that cannot work for that value.", "Trace the failing input with a small example. Which variable is used before it has a suitable value?", "Write the expected state in plain language at each step, then compare it with your attempt."]
    else:
        texts = ["Compare the failing input, your result and the expected result. What needs to be remembered between iterations?", "Try a smaller input with two qualifying items. Preserve the first result while inspecting the second.", "Plan three stages: initialise once, inspect and update repeatedly, then return after the repeated work."]
    return {"text": texts[min(level-1, len(texts)-1)], "line": line,
            "basis": {"input": failed["input"], "actual": failed.get("actual"), "expected": failed["expected"], "error": failed.get("error")},
            "provider": "local", "level": level}
