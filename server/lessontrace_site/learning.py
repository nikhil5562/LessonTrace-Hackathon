"""Evidence-led practice progression and in-workspace help. No model awards mastery."""
from __future__ import annotations
import ast
import asyncio
import hashlib
import json
import time
import re

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal

from .guest import validate
from .learning_content import TOPICS, TASKS, public_task, public_topic
from .meta import MetaUnavailable


class PredictInput(BaseModel):
    question_id: str
    answer: str = Field(max_length=200)


class AttemptInput(BaseModel):
    task_id: str
    source: str = Field(min_length=1, max_length=8000)
    trace_case: int = Field(default=0, ge=0, le=9)
    origin: Literal["learner", "qa_walkthrough"] = "learner"


class ExploreInput(BaseModel):
    source: str = Field(min_length=1, max_length=8000)
    origin: Literal["learner", "qa_walkthrough"] = "learner"


class CoachInput(BaseModel):
    task_id: str
    question: str = Field(min_length=1, max_length=1000)
    source: str = Field(default="", max_length=8000)
    run_id: str | None = None
    step: int = Field(default=0, ge=0, le=350)
    provider: Literal["local", "meta"] = "local"
    consent: bool = False
    video_source_id: str | None = Field(default=None,max_length=100)


class SourceInput(BaseModel):
    url: str = Field(max_length=250)
    notes: str = Field(default="", max_length=5000)
    reviewed: bool = False


def topic_runs(store, who, topic):
    with store.db() as db:
        rows = db.execute("SELECT * FROM runs WHERE owner=? AND mode LIKE 'guided:%' ORDER BY created DESC LIMIT 500", (who,)).fetchall()
    result = []
    for row in rows:
        run = dict(row)
        identifier = run["mode"].split(":", 1)[1]
        if identifier in TASKS and TASKS[identifier]["topic"] == topic:
            run["report"] = json.loads(run["report"]) if run["report"] else {}
            result.append(run)
    return result


def learning_state(store, who, topic):
    progress = store.progress(who)
    predictions = progress.get("learning_prediction_" + topic, [])
    runs = topic_runs(store, who, topic)
    passed = [r for r in runs if r["status"] == "complete" and r["report"].get("all_passed")]
    def independent(run):
        return not run["hints"] and not run["solution_viewed"] and not run["report"].get("assisted_before") and not progress.get("learning_solution_" + run["mode"].split(":", 1)[1])
    steps = []
    selected = None
    for stage in ("repair", "write", "transfer"):
        candidates = [t for t in TASKS.values() if t["topic"] == topic and t["stage"] == stage]
        matches = [r for r in passed if r["mode"].split(":", 1)[1] in {t["id"] for t in candidates}]
        unaided = [r for r in matches if independent(r)]
        done = bool(matches) if stage != "transfer" else bool(unaided)
        steps.append({"stage": stage, "status": "independent checks passed" if unaided else "passed with support" if matches else "not checked", "done": done})
        if not done and selected is None:
            attempted_with_help = {r["mode"].split(":", 1)[1] for r in matches}
            selected = next((t for t in candidates if t["id"] not in attempted_with_help), candidates[-1])
    prediction_ok = bool(predictions and predictions[-1]["correct"])
    if not prediction_ok:
        selected = next(t for t in TASKS.values() if t["topic"] == topic and t["stage"] == "repair")
    independent_transfer = [r for r in passed if TASKS[r["mode"].split(":",1)[1]]["stage"] == "transfer" and independent(r)]
    complete = prediction_ok and all(step["done"] for step in steps)
    due = independent_transfer[0]["created"] + 86400 if complete and independent_transfer else None
    question = TOPICS[topic]["prediction"][len(predictions) % len(TOPICS[topic]["prediction"])]
    return {"topic": public_topic(topic), "prediction_ok": prediction_ok,
        "question": {k:v for k,v in question.items() if k not in {"answer", "why"}},
        "steps": steps, "complete": complete, "review_due_at": due,
        "next_task": public_task(selected) if selected else None,
        "last_task": public_task(TASKS[runs[0]["mode"].split(":",1)[1]]) if runs else None,
        "explanation": "These checks show this session's performance, not durable mastery. Review tomorrow with a fresh task." if complete else "Repair, then write, then try a fresh task. Help and solution access are recorded separately.",
        "attempts": [{"id":r["id"], "task_id":r["mode"].split(":",1)[1], "status":r["status"], "passed":r["report"].get("all_passed",False), "hints":r["hints"], "solution_viewed":bool(r["solution_viewed"]), "independent":independent(r), "created":r["created"], "origin":r["report"].get("origin","learner")} for r in runs[:30]],
        "messages": progress.get("learning_messages_" + topic, []), "source": progress.get("learning_source_" + topic)}


def local_answer(topic, task, question, report=None, step=0):
    text = question.lower()
    notes = TOPICS[topic]["notes"]
    all_notes = {n["id"]:n for t in TOPICS.values() for n in t["notes"]}
    if report and ("step" in text or "line" in text or "this" in text):
        events = report.get("trace", [])
        if events:
            event = events[min(step, len(events)-1)]
            if event.get("error"):
                message = f"On executed line {event['line']}, Python raised {event['error']['type']}: {event['error']['message']}. Inspect the lookup and the actual keys in the boxes."
            elif event.get("control"):
                control = event["control"]
                message = f"The observed {control['action']} targets the nearest loop, which starts on line {control['loop_line']}. Compare the two loop fingers before the next step."
            elif "condition" in event:
                message = f"The condition on executed line {event['line']} evaluated to {event['condition']}. Compare its operands in the recorded state, then predict the next branch."
            else:
                message = f"You selected the state after line {event['line']} actually executed. Compare it with the previous step: which name, object or printed output changed?"
            return {"answer":message, "sources":[notes[0]["id"]], "provider":"local", "label":"Local trace-based explanation"}
    selected = None
    for terms, identifier in [(("popitem",),"dict-methods"), ((".items", "items()", "view", "unpack", ".get"),"dict-methods"), (("break", "continue"),"nested-break"), (("else",),"nested-else"), (("nested", "inner", "outer"),"nested-order"), (("append", "concaten", "a +=", "a = a +"),"list-methods"), (("while", "range", "for loop"),"loop-basics"), (("copy", "reference", "rebind", "assignment", "mutat"),"shared-object"), (("keyerror", "case-sensitive", "capital", "city", "key"),"dict-case"), (("return", "print", "function", "def ", "parameter", "argument", "call"),"function-return"), (("count", "sum", "total", "counter", "+="),"count-state"), (("threshold", "greater", "boundary"),"count-boundary")]:
        if any(term in text for term in terms):
            selected = all_notes[identifier]
            break
    if "len" in text:
        return {"answer":"len(collection) returns its number of items; len('Devika') is 6. It does not add numeric values." + (" This counting unit asks you to practise updating a counter in an explicit loop." if topic=="counting" else ""), "sources":["function-return"], "provider":"local", "label":"Local prerequisite explanation"}
    if "hint" in text or "stuck" in text or "help" in text:
        selected = {"id":task["sources"][0], "text": task["hint"]}
    if selected:
        return {"answer":selected["text"], "sources":[selected["id"]], "provider":"local", "label":"Local authored explanation"}
    return {"answer":"Tell me which expression or trace line is confusing. Local help covers the supplied concepts; choose Meta for a more specific explanation of your current code.", "sources":[notes[0]["id"]], "provider":"local", "label":"Local help scope"}


def install_learning_routes(app, owner, store, execution, meta, reserve_cloud, tasks, semaphore):
    def require_topic(topic):
        if topic not in TOPICS:
            raise HTTPException(404, "Practice unit not found.")

    @app.get("/api/learning")
    async def catalog(request: Request):
        owner(request)
        return {"topics":[{"id":k,"title":v["title"],"subtitle":v["subtitle"]} for k,v in TOPICS.items()], "glossary":[n for t in TOPICS.values() for n in t["notes"]]}

    @app.get("/api/learning/{topic}")
    async def current(topic: str, request: Request):
        require_topic(topic)
        return learning_state(store, owner(request), topic)

    @app.post("/api/learning/{topic}/predict")
    async def predict(topic: str, body: PredictInput, request: Request):
        require_topic(topic)
        who = owner(request, True)
        before = learning_state(store, who, topic)
        if body.question_id != before["question"]["id"]:
            raise HTTPException(409, "The prediction changed; reload this unit.")
        question = next(q for q in TOPICS[topic]["prediction"] if q["id"] == body.question_id)
        if body.answer not in question["options"]:
            raise HTTPException(422, "Choose one of the available predictions.")
        history = store.progress(who).get("learning_prediction_"+topic, [])
        correct = body.answer == question["answer"]
        store.set_progress(who, "learning_prediction_"+topic, (history + [{"id":body.question_id,"answer":body.answer,"correct":correct,"at":time.time()}])[-100:])
        return {"correct":correct,"feedback":question["why"],"state":learning_state(store, who, topic)}

    async def job(who, identifier, source, arguments, entry, task, trace_case, origin):
        try:
            async with semaphore:
                store.finish_run(who, identifier, "running")
                raw = await execution.execute({"source":source,"arguments":arguments,"entry":entry,"trace_case":trace_case})
                if raw.get("error"):
                    store.finish_run(who, identifier, "failed", raw)
                    return
                if raw.get("source_sha256") != hashlib.sha256(source.encode()).hexdigest() or len(raw.get("cases",[])) != len(arguments):
                    raise ValueError("Execution provenance mismatch")
                checks=[]
                for index, case in enumerate(raw["cases"]):
                    if task:
                        expected=task["cases"][index]["expected"]
                        unchanged = True if task["topic"] != "dictionary" else case.get("arguments_after") == arguments[index] if "arguments_after" in case else None
                        checks.append({"input":arguments[index],"expected":expected,"actual":case.get("actual"),"error":case.get("error"),"input_unchanged":unchanged,
                            "passed":not case.get("error") and case.get("return_type")==type(expected).__name__ and case.get("actual")==expected and unchanged is not False})
                chosen=raw["cases"][trace_case]
                report={"source":source,"source_hash":raw["source_sha256"],"runtime":raw["runtime"],"trace":chosen.get("events",[]),"actual":chosen.get("actual"),"error":chosen.get("error"),"output":chosen.get("output",""),"checks":checks,"all_passed":bool(checks) and all(c["passed"] for c in checks),"origin":origin,"trace_case":trace_case,"assisted_before":False}
                if task:
                    report["assisted_before"] = bool(store.progress(who).get("learning_help_"+task["id"]))
                store.finish_run(who, identifier, "complete", report)
        except asyncio.CancelledError:
            store.cancel_run(who, identifier)
            raise
        except Exception:
            store.finish_run(who, identifier, "failed", {"error":{"type":"RunnerUnavailable","message":"The checked run could not finish within the pilot limits."}})
        finally:
            tasks.pop(identifier,None)

    def start(who, source, arguments, entry, task, trace_case, origin):
        if not execution.ready:
            raise HTTPException(503, execution.error or "Python is warming up.")
        if len(tasks)>=6:
            raise HTTPException(429,"Wait for the current Python runs to finish.")
        try:
            tree=validate(source,entry)
            if task and (task["topic"]=="counting" or task.get("requires_loop")):
                if not any(isinstance(n,(ast.For,ast.While)) for n in ast.walk(tree)) or any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {"sum","len"} for n in ast.walk(tree)):
                    raise ValueError("Practise the explicit loop and accumulator for this task.")
            if task and task["topic"]=="nested":
                if not any(isinstance(n,ast.For) and n.orelse and any(isinstance(outer,ast.For) and outer is not n and n in list(ast.walk(outer)) for outer in ast.walk(tree)) for n in ast.walk(tree)):
                    raise ValueError("This unit practises two nested for loops and the inner for-else.")
            identifier=store.create_run(who,"guided:"+task["id"] if task else "explore",source,hashlib.sha256(source.encode()).hexdigest())
        except (SyntaxError,ValueError) as error:
            raise HTTPException(422,str(error)[:300]) from None
        tasks[identifier]=asyncio.create_task(job(who,identifier,source,arguments,entry,task,trace_case,origin))
        return {"id":identifier,"status":"queued"}

    @app.post("/api/learning/attempt")
    async def attempt(body: AttemptInput, request: Request):
        who=owner(request,True)
        task=TASKS.get(body.task_id)
        if not task:
            raise HTTPException(404,"Task not found.")
        state=learning_state(store,who,task["topic"])
        prior = any(r["task_id"]==task["id"] for r in state["attempts"])
        if not state["prediction_ok"] or (not prior and (not state["next_task"] or state["next_task"]["id"]!=task["id"])):
            raise HTTPException(409,"Complete the prediction and current task before moving on.")
        if body.trace_case>=len(task["cases"]):
            raise HTTPException(422,"Choose one of this task's checks.")
        return start(who,body.source,[c["args"] for c in task["cases"]],task["entry"],task,body.trace_case,body.origin)

    @app.post("/api/learning/explore")
    async def explore(body: ExploreInput, request: Request):
        return start(owner(request,True),body.source,[[]],None,None,0,body.origin)

    @app.post("/api/learning/{topic}/coach")
    async def coach(topic: str, body: CoachInput, request: Request):
        require_topic(topic)
        who=owner(request,True)
        task=TASKS.get(body.task_id)
        if not task or task["topic"]!=topic:
            raise HTTPException(422,"Choose a task in the current unit.")
        report=None
        run=None
        if body.run_id:
            run=store.get_run(who,body.run_id)
            if not run or run["mode"] not in {"guided:"+task["id"],"explore"} or run["status"]!="complete" or run["source"]!=body.source:
                raise HTTPException(409,"Run this exact code before asking about its trace.")
            report=run["report"]
        if body.provider=="meta":
            reserve_cloud(who,body.consent,"guided practice question")
            notes=[n for t in TOPICS.values() for n in t["notes"]]
            evidence={"question":body.question,"task":task["task"],"current_source":body.source,"lesson_notes":notes,"observed_checks":report.get("checks",[]) if report else [],"selected_trace_step":report.get("trace",[])[min(body.step,len(report["trace"])-1)] if report and report.get("trace") else None,"code_checked":bool(report)}
            evidence["recent_conversation"] = [{"question":m["question"][:400],"answer":m["answer"][:900]} for m in store.progress(who).get("learning_messages_"+topic,[])[-6:]]
            attached=store.progress(who).get("learning_source_"+topic)
            if attached and attached.get("reviewed") and attached.get("notes"):
                evidence["learner_reviewed_notes"]=attached["notes"]
            video=store.progress(who).get("youtube_session")
            video_sources=[]
            if video:
                words=set(re.findall(r'[a-z]{3,}',body.question.lower()))
                chunks=sorted(video.get("caption_chunks",[]),key=lambda c:(c['id']==body.video_source_id,len(words & set(re.findall(r'[a-z]{3,}',c['text'].lower())))),reverse=True)[:3]
                evidence['video_caption_excerpts']=chunks
                video_sources=[c['id'] for c in chunks]
            try:
                answer=await meta.generate("You are a patient Python learning coach beside an editor and real execution trace. Answer the specific question in plain language in at most 170 words. Use Python value names such as None, True and False; avoid JSON transport terms such as null. Describe exactly which part worked and which checks failed. Use recent conversation to understand follow-ups, but treat learner guesses as unverified. Use real Python terms consistently; use at most one analogy, and drop it if confusing. Separate existing object mutation from name rebinding, list concatenation from numeric addition, and inner break from outer iteration. Explain unknown functions before using them. Give one small follow-up prediction, not a full worked solution. When code is unchecked, say so; when all checks pass, acknowledge that evidence accurately. Never invent a KeyError or award mastery. Cite supplied lesson-note IDs. Distinguish observed state from your explanation.",evidence,[n["id"] for n in notes]+video_sources)
                answer["label"]="Meta-generated · Muse Spark 1.3"
            except MetaUnavailable as error:
                raise HTTPException(503,str(error)) from None
        else:
            answer=local_answer(topic,task,body.question,report,body.step)
        if run and run["mode"].startswith("guided:"):
            store.hint_level(who,run["id"])
        store.set_progress(who,"learning_help_"+task["id"],True)
        messages=store.progress(who).get("learning_messages_"+topic,[])
        messages=(messages+[{"question":body.question,"answer":answer["answer"],"provider":answer["provider"],"sources":answer["sources"],"task_id":task["id"]}])[-24:]
        store.set_progress(who,"learning_messages_"+topic,messages)
        return {**answer,"allowance":store.provider_allowance()}

    @app.post("/api/learning/{topic}/source")
    async def attach_source(topic: str, body: SourceInput, request: Request):
        require_topic(topic)
        who=owner(request,True)
        match=re.fullmatch(r"https://(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_-]{11})(?:&[^\s]*)?|https://youtu\.be/([A-Za-z0-9_-]{11})(?:\?[^\s]*)?",body.url.strip())
        if not match:
            raise HTTPException(422,"Use a YouTube watch or youtu.be video link.")
        if body.notes.strip() and not body.reviewed:
            raise HTTPException(409,"Review your notes before attaching them as learning context.")
        identifier=match.group(1) or match.group(2)
        store.set_progress(who,"learning_source_"+topic,{"video_id":identifier,"url":"https://www.youtube.com/watch?v="+identifier,"notes":body.notes.strip(),"reviewed":body.reviewed,"coverage":"Reference link and learner-reviewed notes; no automatic full-video analysis."})
        return {"saved":True,"source":store.progress(who)["learning_source_"+topic]}

    @app.post("/api/learning/{topic}/solution")
    async def reveal(topic: str, body: CoachInput, request: Request):
        require_topic(topic)
        who=owner(request,True)
        task=TASKS.get(body.task_id)
        run=store.get_run(who,body.run_id or "")
        if not task or task["topic"]!=topic or not run or run["mode"]!="guided:"+task["id"] or run["status"]!="complete":
            raise HTTPException(409,"Check an attempt before explicitly revealing its solution.")
        store.mark_solution(who,run["id"],run["mode"])
        store.set_progress(who,"learning_solution_"+task["id"],True)
        return {"source":task["solution"],"label":"Solution accessed: this task is no longer independent evidence."}
