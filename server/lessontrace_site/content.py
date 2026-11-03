"""Original pilot lesson and independently authored exercise oracles."""

COLLECT = """def collect_heavy_rain(rainfall):
    heavy = []
    for mm in rainfall:
        if mm > 20:
            heavy.append(mm)
    return heavy
"""
REFERENCES = """a = [1, 2]
c = [9, 9]
b = a
a = c
c.append(0)
print(a, b, c)
"""
COUNT_SOLUTION = """def count_heavy(rainfall):
    count = 0
    for mm in rainfall:
        if mm > 20:
            count += 1
    return count
"""
NAMES_SOLUTION = """def collect_long_names(names):
    selected = []
    for name in names:
        if len(name) > 6:
            selected.append(name)
    return selected
"""

LESSON = {
    "id": "rainfall-patterns-v1", "revision": 1,
    "title": "See the pattern behind a loop",
    "subtitle": "Build a list, understand the state, then solve a fresh task.",
    "source_kind": "Original authored lesson and prepared notes",
    "concepts": ["functions", "lists", "for loops", "comparisons", "append", "return", "counters"],
    "example_source": COLLECT, "example_input": [5, 22, 20, 45],
    "segments": [
        {"id": "source-1", "title": "Start with the question", "text": "We have rainfall readings: 5, 22, 20 and 45 millimetres. For this programming exercise, collect the readings strictly greater than 20. Twenty is an example threshold, not a weather classification or a school-closure rule."},
        {"id": "source-2", "title": "Remember progress", "text": "Create an empty list named heavy before the loop. This list remembers the qualifying readings we have found so far. Creating it inside the loop would throw away previous progress."},
        {"id": "source-3", "title": "Inspect one reading at a time", "text": "A for loop gives mm the next reading on each iteration. Ask whether mm is greater than 20. Five fails. Twenty-two passes. Exactly twenty fails. Forty-five passes."},
        {"id": "source-4", "title": "Change the list", "text": "When the comparison is true, append mm to heavy. Append changes the same list object. After twenty-two, heavy contains twenty-two. After forty-five it contains twenty-two and forty-five."},
        {"id": "source-5", "title": "Return the result", "text": "Return heavy after the loop finishes, so the caller receives the completed list. Printing displays text; returning sends a value to the caller. Returning inside the loop ends the function before all readings have been inspected."},
        {"id": "source-6", "title": "Change what you remember", "text": "For a counting task, remember a number instead of a list. Start a count at zero before the loop, increase it by one when a reading qualifies, and return the count after the loop. The comparison stays the same; the accumulated state changes."},
        {"id": "source-7", "title": "Apply the idea elsewhere", "text": "Python strings can also be placed in a list. The expression len(name) returns the number of characters in a name. After reviewing this prerequisite, use the same inspect, compare and remember pattern to collect names longer than six characters."},
    ],
    "notes": [
        {"id": "note-1", "title": "Choose the state from the question", "text": "Collecting needs a list; counting needs a number. Decide what the caller should receive before writing the loop.", "sources": ["source-1", "source-2", "source-6"]},
        {"id": "note-2", "title": "Initialise once, update repeatedly", "text": "Initialise your result before the loop. Each iteration should preserve earlier progress and update it only when appropriate.", "sources": ["source-2", "source-4", "source-6"]},
        {"id": "note-3", "title": "Make the boundary explicit", "text": "Strictly greater than 20 means exactly 20 does not qualify. Include this case when checking your program.", "sources": ["source-1", "source-3"]},
        {"id": "note-4", "title": "Return after all the work", "text": "Return the completed value after the loop. Keep printed output and returned values separate when debugging.", "sources": ["source-5"]},
    ],
}

EXERCISES = {
    "count": {
        "id": "count", "title": "Count the qualifying readings", "entry": "count_heavy",
        "task": "Write count_heavy(rainfall). Return how many readings are strictly greater than 20. Use a loop and a counter. An empty list returns 0. Do not use sum() or len() for the count.",
        "starter": "def count_heavy(rainfall):\n    # Write your plan, then your code.\n    pass\n",
        "cases": [([5, 22, 20, 45], 2), ([], 0), ([20], 0), ([21], 1), ([21, 21], 2), ([30, 5, 22], 2)],
        "solution": COUNT_SOLUTION, "prerequisites": ["functions", "lists", "loops", "comparison", "counter"],
        "sources": ["source-3", "source-5", "source-6"],
    },
    "transfer": {
        "id": "transfer", "title": "A fresh context: collect long names", "entry": "collect_long_names",
        "task": "Write collect_long_names(names). Return a new list containing names longer than 6 characters, in the original order. Exactly 6 characters does not qualify. Empty input returns []. Review the string-length prerequisite first.",
        "starter": "def collect_long_names(names):\n    # What should remember your progress?\n    pass\n",
        "cases": [(["Anu", "Devika", "Lakshmi", "Sreelakshmi"], ["Lakshmi", "Sreelakshmi"]), ([], []), (["Devika"], []), (["Lakshmi"], ["Lakshmi"]), (["Lakshmi", "Lakshmi"], ["Lakshmi", "Lakshmi"])],
        "solution": NAMES_SOLUTION, "prerequisites": ["strings", "len", "list building"],
        "sources": ["source-4", "source-5", "source-7"],
    },
}


def public_lesson():
    return {**LESSON, "exercises": [{k: v for k, v in exercise.items() if k != "solution"} for exercise in EXERCISES.values()], "reference_source": REFERENCES}
