"""Original short lessons and bounded practice variants, authored 30 October 2026.

Reference products informed the interaction pattern, not the exercise text/oracles.
"""
from copy import deepcopy

TOPICS = {
    "counting": {
        "title": "Count, don't add", "subtitle": "Keep a running count while inspecting one item at a time.",
        "notes": [
            {"id": "count-state", "title": "What are you remembering?", "text": "A counter answers how many. Initialise count = 0 once before the loop. For each qualifying item, count += 1. Adding the item itself answers a different question: the total of the values."},
            {"id": "count-boundary", "title": "Test the exact boundary", "text": "Strictly greater than a threshold excludes the threshold itself. For > 20, 20 fails and 21 passes. An empty input still returns the initial count of zero."},
            {"id": "function-return", "title": "Define, call, return", "text": "def names a reusable block and its parameters. A call supplies arguments. return sends a value to the caller and exits the function immediately; print displays text. Return the accumulated result after all required iterations."},
            {"id": "loop-basics", "title": "For, while and range", "text": "A for loop requests each item of its iterable in order. range(3) supplies 0, 1, 2. A while loop checks its condition before each iteration; the body needs a way to make that condition false or exit through break. An unchanged true condition can loop forever."},
            {"id": "list-methods", "title": "Append changes a list", "text": "values.append(x) adds x as one item to the end of the existing list and returns None. It does not make a new list. For lists, a + [x] creates a new concatenated list; a += [x] extends the existing list. These are different from arithmetic on the numbers inside the list."},
        ],
        "prediction": [
            {"id": "count-p1", "prompt": "For [5, 22, 20, 45], how many values are strictly greater than 20?", "options": ["2", "3", "67"], "answer": "2", "why": "Only 22 and 45 qualify. Counting those two items gives 2; their total, 67, answers a different question."},
            {"id": "count-p2", "prompt": "For [8, 8, 7], how many values are strictly greater than 7?", "options": ["16", "2", "3"], "answer": "2", "why": "Both eights qualify; seven does not. Each match adds one to the count."},
        ],
        "example": "def count_readings(values):\n    count = 0\n    for value in values:\n        if value > 20:\n            count += 1\n    return count\n\nprint(count_readings([5, 22, 20, 45]))\n",
    },
    "dictionary": {
        "title": "Follow a dictionary lookup", "subtitle": "Choose the outer entry, then the key inside it.",
        "notes": [
            {"id": "dict-path", "title": "Two lookups, in order", "text": 'airports[code]["city"] first reads the dictionary stored under code, then reads its "city" value. Python does not guess the key from the surrounding text.'},
            {"id": "dict-case", "title": "Keys match exactly", "text": '"city" and "City" are different string keys. A missing key raises KeyError at the attempted lookup. If the correct keys are already present in the code, check the actual output before describing a bug.'},
            {"id": "dict-methods", "title": "Know what each method returns", "text": ".items() returns a live view of key-value pairs; a loop can unpack each pair into two names. .get(key, default) provides a default for a missing key. .pop(key) removes that entry and returns its value; a missing key raises KeyError unless a default is supplied. .popitem() removes and returns the last inserted pair; it raises KeyError when the dictionary is empty. An empty dictionary is false in a condition."},
            {"id": "shared-object", "title": "Names and shared objects", "text": "Assignment binds a name to an object without copying it. A loop over a list of dictionaries hands you each dictionary object. Editing item['quantity'] changes that object; assigning item = {...} only changes what that name refers to. A shallow copy creates a new outer container but can still share nested objects."},
        ],
        "prediction": [
            {"id": "dict-p1", "prompt": 'The dictionary is {"LHR": {"city": "London", "country": "UK"}}. What does airports["LHR"]["city"] return?', "options": ["London", "LHR", "KeyError"], "answer": "London", "why": '"LHR" selects the inner dictionary; "city" selects "London". These keys already match.'},
            {"id": "dict-p2", "prompt": 'The inner dictionary contains "city". What happens when the code reads ["City"] instead?', "options": ["London", "KeyError", "It changes the key"], "answer": "KeyError", "why": 'Dictionary string keys are case-sensitive. "City" is not the stored key "city".'},
        ],
        "example": 'airports = {"LHR": {"city": "London", "country": "UK"}}\nselected = airports["LHR"]\nprint(selected["city"], "-", selected["country"])\n',
    },
    "nested": {
        "title": "Two loops, two fingers", "subtitle": "Watch the inner search restart for each outer item.",
        "notes": [
            {"id": "nested-order", "title": "One outer item, a new inner search", "text": "A for loop over a list visits its items in order. For each outer item, a new inner loop starts at its first item. Keep a separate finger for each loop and match each finger to its own iterable."},
            {"id": "nested-break", "title": "Which loop does break exit?", "text": "break exits the nearest enclosing loop. Breaking an inner search leaves the outer loop free to continue with its next item. continue skips the remaining statements of the current iteration of its nearest loop."},
            {"id": "nested-else", "title": "The indentation tells you whose else", "text": "A for-else block belongs to the for at the same indentation. The else runs after normal exhaustion, including an empty search, and is skipped when that loop exits through break. A completed inner search does not end the outer loop."},
        ],
        "prediction": [
            {"id": "nested-p1", "prompt": "An inner search finds its first match and executes break. What happens next?", "options": ["Both loops end", "The outer loop can continue", "The inner else always runs"], "answer": "The outer loop can continue", "why": "break exits the nearest loop: the inner search. Its else is skipped; the outer loop can inspect its next item."},
            {"id": "nested-p2", "prompt": "The inner search checks an empty list and has a for-else block. What happens?", "options": ["Its else runs", "Its else is skipped", "Both loops raise KeyError"], "answer": "Its else runs", "why": "There was normal exhaustion without a break, so the inner for's else runs even with zero iterations."},
        ],
        "example": 'required = ["torch", "map"]\npacked = ["torch", "water"]\nfor needed in required:\n    for item in packed:\n        if item == needed:\n            print("found", needed)\n            break\n    else:\n        print("missing", needed)\n',
    },
}

TASKS = {}


def counting(identifier, stage, threshold, noun, repair=False, total=False):
    entry = identifier.replace("-", "_")
    variable = "total" if total else "count"
    increment = "value" if total else "1"
    solution = f"def {entry}(values):\n    {variable} = 0\n    for value in values:\n        if value > {threshold}:\n            {variable} += {increment}\n    return {variable}\n"
    cases = [([threshold-2, threshold+2, threshold, threshold+5], (2*threshold+7) if total else 2), ([], 0), ([threshold], 0), ([threshold+1], threshold+1 if total else 1), ([threshold+1, threshold+1], 2*(threshold+1) if total else 2)]
    TASKS[identifier] = {"id": identifier, "topic": "counting", "stage": stage, "entry": entry,
        "title": ("Repair: " if repair else "Write: ") + ("add the qualifying values" if total else "count the qualifying values"),
        "task": f"Write {entry}(values). {'Add the values of' if total else 'Count'} the {noun} that are strictly greater than {threshold}. Return the resulting number. Use an explicit loop. Empty input returns 0.",
        "starter": solution.replace("+= 1", "+= value") if repair else f"def {entry}(values):\n    # Choose what to remember before writing the loop.\n    pass\n",
        "solution": solution, "cases": [{"args": [values], "expected": expected} for values, expected in cases],
        "sources": ["count-state", "count-boundary", "function-return"], "threshold": threshold,
        "hint": "Compare counting matches with adding their values. Start your accumulator before the loop, update it on a match, and return it after the loop."}


counting("count-rain", "repair", 20, "readings", repair=True)
counting("count-parcels", "write", 7, "parcel weights")
counting("sum-readings", "transfer", 12, "readings", total=True)
counting("sum-scores", "transfer", 8, "scores", total=True)

for identifier, stage, key, repair in [("airport-label", "repair", "city", True), ("station-label", "write", "town", False), ("venue-label", "transfer", "name", False), ("harbour-label", "transfer", "place", False)]:
    entry = identifier.replace("-", "_")
    data = {"A1": {key: "Kochi", "country": "India"}, "B2": {key: "Osaka", "country": "Japan"}}
    solution = f'def {entry}(locations, code):\n    selected = locations[code]\n    return selected["{key}"] + " - " + selected["country"]\n'
    TASKS[identifier] = {"id": identifier, "topic": "dictionary", "stage": stage, "entry": entry,
        "title": ("Repair: exact keys" if repair else "Write: a fresh nested lookup"),
        "task": f'Write {entry}(locations, code). Read the nested "{key}" and "country" values and return "place - country" using the actual values. All requested outer codes exist. Keep the input unchanged.',
        "starter": solution.replace(f'"{key}"', f'"{key.title()}"') if repair else f"def {entry}(locations, code):\n    pass\n",
        "solution": solution, "cases": [{"args": [deepcopy(data), "A1"], "expected": "Kochi - India"}, {"args": [deepcopy(data), "B2"], "expected": "Osaka - Japan"}, {"args": [{"Z9": {key: "London", "country": "UK"}}, "Z9"], "expected": "London - UK"}],
        "sources": ["dict-path", "dict-case"], "hint": "Read the actual keys in the failing input. First select the outer code, then compare the exact spelling and case of each inner key."}

for identifier, stage, repair in [("missing-gear", "repair", True), ("missing-books", "write", False), ("missing-tools", "transfer", False), ("missing-parts", "transfer", False)]:
    entry = identifier.replace("-", "_")
    a,b,c={"missing-gear":("torch","map","rope"),"missing-books":("atlas","novel","poems"),"missing-tools":("saw","drill","hammer"),"missing-parts":("cog","spring","bolt")}[identifier]
    solution = f"def {entry}(required, available):\n    missing = []\n    for needed in required:\n        for item in available:\n            if item == needed:\n                break\n        else:\n            missing.append(needed)\n    return missing\n"
    TASKS[identifier] = {"id": identifier, "topic": "nested", "stage": stage, "entry": entry,
        "title": "Repair: finish the whole checklist" if repair else "Write: search, then report missing items",
        "task": f"Write {entry}(required, available). Return required items absent from available, preserving order and duplicates. Practise two for loops and the inner for-else. Empty required returns []; empty available means every required item is missing.",
        "starter": solution.replace("    return missing", "        return missing") if repair else f"def {entry}(required, available):\n    pass\n",
        "solution": solution, "cases": [{"args": [[a,b,c], [a,c]], "expected": [b]}, {"args": [[], [a]], "expected": []}, {"args": [[b,b], []], "expected": [b,b]}, {"args": [[b,a], [a,b]], "expected": []}, {"args": [[c,a,b], [b]], "expected": [c,a]}],
        "sources": ["nested-order", "nested-break", "nested-else"], "hint": "Track one outer item and one inner search separately. An inner break only stops that search. Check the indentation of return: have all required items been visited?"}


from .functions_unit import add_functions
add_functions(TOPICS, TASKS)


def public_task(task):
    return {key: deepcopy(value) for key, value in task.items() if key not in {"solution", "hint"}}


def public_topic(identifier):
    topic = deepcopy(TOPICS[identifier])
    topic["id"] = identifier
    topic["prediction"] = [{k: v for k, v in item.items() if k not in {"answer", "why"}} for item in topic["prediction"]]
    return topic
