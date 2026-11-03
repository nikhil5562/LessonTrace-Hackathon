"""Local website pilot; immutable source, owned attempts and execution-grounded help."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import secrets
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .content import COLLECT, EXERCISES, LESSON, REFERENCES, public_lesson
from .guest import validate as validate_source
from .hints import local_hint
from .meta import MetaProvider, MetaUnavailable
from .runner import ROOT, WasiRunner
from .store import Store
from .learning import install_learning_routes
from .video_lessons import install_video_routes
from .video_learning import install_video_learning_routes
from .hub import install_hub_routes
from .learning_coach import LearningCoach,install_coach_routes
from .provider_audit import AuditedProvider

SOURCE_HASH = hashlib.sha256(json.dumps(LESSON, sort_keys=True).encode()).hexdigest()


class Prediction(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    mode: Literal["example", "references"] = "example"


class RunInput(BaseModel):
    mode: Literal["example", "references", "count", "transfer"]
    source: str = Field(default="", max_length=8000)
    trace_case: int = Field(default=0, ge=0, le=5)
    origin: Literal["learner", "qa_walkthrough"] = "learner"


class HintInput(BaseModel):
    run_id: str
    provider: Literal["local", "meta"] = "local"
    consent: bool = False


class CloudInput(BaseModel):
    consent: bool = False


class PackInput(BaseModel):
    text: str = Field(min_length=20, max_length=16000)


class ReviewInput(BaseModel):
    reviewed: bool


def create_app(data_dir=None, runner=None, provider=None, hub_loader=None,course_content_root=None,course_source_reader=None):
    data = Path(data_dir or os.environ.get("LESSONTRACE_DATA_DIR", ROOT / ".local"))
    store = Store(data / "lessontrace.sqlite3", None,
                  provider_limit_cents=int(os.environ.get("LESSONTRACE_TEST_LIMIT_CENTS", "100")))
    execution = runner or WasiRunner(data)
    meta = AuditedProvider(provider or MetaProvider(),store,execution)
    signing_key = secrets.token_bytes(32)
    tasks = {}
    warm_task = None
    semaphore = asyncio.Semaphore(2)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal warm_task
        warm_task = asyncio.create_task(execution.warmup())
        yield
        for task in list(tasks.values()):
            task.cancel()
        if warm_task:
            warm_task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        if warm_task:
            await asyncio.gather(warm_task, return_exceptions=True)
        await execution.close()

    app = FastAPI(title="LessonTrace local pilot", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.state.store, app.state.runner = store, execution

    def csrf(token):
        return hmac.new(signing_key, token.encode(), hashlib.sha256).hexdigest()

    def owner(request, mutation=False):
        token = request.cookies.get("lessontrace_browser", "")
        if not re.fullmatch(r"[a-f0-9]{48}", token):
            raise HTTPException(401, "Open the lesson page to start your private local session.")
        if mutation:
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if origin and origin != expected or request.headers.get("sec-fetch-site") == "cross-site":
                raise HTTPException(403, "This request must come from the LessonTrace page.")
            if not hmac.compare_digest(request.headers.get("x-lessontrace-csrf", ""), csrf(token)):
                raise HTTPException(403, "Refresh the lesson page and try again.")
        return hashlib.sha256(token.encode()).hexdigest()

    def owned_run(who, identifier):
        run = store.get_run(who, identifier)
        if not run:
            raise HTTPException(404, "Attempt not found in this browser's session.")
        return run

    def reserve_cloud(who, consent, purpose):
        if not meta.enabled:
            raise HTTPException(409, "Meta calls are paused until funding is verified and the operator explicitly resumes them.")
        if not consent:
            raise HTTPException(409, "Explicitly allow this material to be processed by Meta first.")
        try:
            reservation=store.reserve_provider(who, purpose)
            meta.prepare(who,purpose,reservation)
            return reservation
        except ValueError as error:
            raise HTTPException(429, str(error)) from None

    @app.middleware("http")
    async def response_headers(request, call_next):
        try:
            size = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length."}, status_code=400)
        if size > 40000:
            return JSONResponse({"detail": "Request is too large for this pilot."}, status_code=413)
        request.state.style_nonce=secrets.token_urlsafe(24)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'nonce-"+request.state.style_nonce+"'; img-src 'self' data:; connect-src 'self'; media-src 'self'; frame-src https://www.youtube-nocookie.com; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    async def home(request: Request):
        page=(ROOT/'app'/'index.html').read_text(encoding='utf-8')
        page=page.replace('</head>','<meta name="lessontrace-style-nonce" content="'+request.state.style_nonce+'"></head>')
        return HTMLResponse(page,headers={'Cache-Control':'no-store'})

    @app.get("/plan/")
    async def plan():
        return FileResponse(ROOT / "plan.html")

    # Mount only deliberately public assets. Never expose the project root or .local.
    for route, directory in (("/static", ROOT / "app" / "assets"), ("/media", ROOT / "app" / "media")):
        app.mount(route, StaticFiles(directory=directory), name=route.replace("/", "-"))

    @app.get("/plan/{name}")
    async def plan_file(name: str):
        if name not in {'README.md','ARCHITECTURE.md','CONFIGURATION.md','CLAIM_REVIEW.md','EVALUATION.md','VALIDATION.md','CONTENT_LICENSE.md','THIRD_PARTY_NOTICES.md'}:
            raise HTTPException(404)
        return FileResponse(ROOT / name)

    @app.get('/plan/evaluation/{name}')
    async def evaluation_file(name: str):
        if name not in {'scenarios.json','results-2026-10-31.json','adversarial-v1.json','claim-review-results-2026-11-02.json','claim-review-followup-2026-11-02.json','rubric-oracles-2026-11-02.json','claim-review-full-2026-11-03.json','course-audit-summary-2026-11-03.json','live-original-2026-11-03.json','demo-video-2026-11-03.json','hub-live-2026-11-03.json','demo-hub-video-2026-11-03.json'}:raise HTTPException(404)
        return FileResponse(ROOT/'evaluation'/name)

    @app.get("/api/session")
    async def session(request: Request, response: Response):
        token = request.cookies.get("lessontrace_browser", "")
        if not re.fullmatch(r"[a-f0-9]{48}", token):
            token = secrets.token_hex(24)
            response.set_cookie("lessontrace_browser", token, httponly=True, samesite="strict", max_age=2592000)
        return {"csrf": csrf(token), "runner": {"ready": execution.ready, "error": execution.error},
                "meta": {"enabled": meta.enabled, "status": "Available on explicit request" if meta.enabled else "Live processing paused; local work is available", "speech": None, "teaching": "muse-spark-1.3", "allowance":store.provider_allowance()},
                "privacy": "Local browser-owned pilot. No hosted accounts or classroom sharing."}

    @app.get("/api/lesson")
    async def lesson():
        return {**public_lesson(), "source_hash": SOURCE_HASH}

    @app.get('/api/meta/activity')
    async def meta_activity(request:Request):
        return {'events':meta.activity_for(owner(request)),'scope':'This browser only; actual provider request status, not a correctness or billing guarantee. Prompts, code and keys are excluded.'}

    @app.get("/api/progress")
    async def progress(request: Request):
        who = owner(request)
        from .video_lessons import public_session
        public_progress={k:v for k,v in store.progress(who).items() if not k.startswith(('video_progress_','hub_','coach_','course_'))}
        if public_progress.get('youtube_session'):public_progress['youtube_session']=public_session(public_progress['youtube_session'])
        return {"progress": public_progress, "runs": store.history(who), "pack": store.get_pack(who)}

    @app.post("/api/prediction")
    async def prediction(body: Prediction, request: Request):
        who = owner(request, True)
        if not body.text.strip():
            raise HTTPException(422, "Write a prediction before revealing execution.")
        source = COLLECT if body.mode == "example" else REFERENCES
        store.set_progress(who, "prediction_" + body.mode, {"text": body.text.strip(), "source_hash": hashlib.sha256(source.encode()).hexdigest()})
        return {"saved": True}

    @app.post("/api/strings-reviewed")
    async def strings_reviewed(request: Request):
        store.set_progress(owner(request, True), "strings_reviewed", True)
        return {"saved": True}

    async def execute_job(who, identifier, body, source):
        try:
            async with semaphore:
                store.finish_run(who, identifier, "running")
                if body.mode in EXERCISES:
                    exercise = EXERCISES[body.mode]
                    arguments = [[case[0]] for case in exercise["cases"]]
                    entry = exercise["entry"]
                else:
                    exercise = None
                    arguments = [[[5, 22, 20, 45]]] if body.mode == "example" else [[]]
                    entry = "collect_heavy_rain" if body.mode == "example" else None
                result = await execution.execute({"source": source, "entry": entry, "arguments": arguments, "trace_case": body.trace_case})
                if "error" in result:
                    store.finish_run(who, identifier, "failed", result)
                    return
                if result.get("source_sha256") != hashlib.sha256(source.encode()).hexdigest() or len(result.get("cases", [])) != len(arguments):
                    raise ValueError("Execution provenance mismatch")
                checks = []
                for index, case in enumerate(result["cases"]):
                    if exercise:
                        expected = exercise["cases"][index][1]
                        checks.append({"input": arguments[index][0], "expected": expected, "actual": case.get("actual"),
                                       "passed": not case.get("error") and type(case.get("actual")) is type(expected) and case.get("actual") == expected,
                                       "output": case.get("output", ""), "error": case.get("error")})
                chosen = result["cases"][body.trace_case]
                report = {"runtime": result["runtime"], "source_hash": result["source_sha256"], "trace": chosen.get("events", []),
                          "source": source, "checks": checks, "actual": chosen.get("actual"), "output": chosen.get("output", ""), "error": chosen.get("error"),
                          "all_passed": bool(checks) and all(c["passed"] for c in checks), "trace_case": body.trace_case,
                          "origin": body.origin,
                          "state_convention": "State after the highlighted executed line"}
                store.finish_run(who, identifier, "complete", report)
        except asyncio.CancelledError:
            store.cancel_run(who, identifier)
            raise
        except Exception:
            store.finish_run(who, identifier, "failed", {"error": {"type": "RunnerUnavailable", "message": "The isolated Python run could not finish. Check runtime status and retry."}})
        finally:
            tasks.pop(identifier, None)

    @app.post("/api/runs", status_code=202)
    async def create_run(body: RunInput, request: Request):
        who = owner(request, True)
        if not execution.ready:
            raise HTTPException(503, execution.error or "Python is warming up. Try again shortly.")
        if len(tasks) >= 6:
            raise HTTPException(429, "The pilot is busy. Wait for the current runs to finish.")
        if body.mode in {"example", "references"}:
            if body.trace_case != 0:
                raise HTTPException(422, "Worked examples have one fixed input.")
            source = COLLECT if body.mode == "example" else REFERENCES
            prediction = store.progress(who).get("prediction_" + body.mode, {})
            if prediction.get("source_hash") != hashlib.sha256(source.encode()).hexdigest():
                raise HTTPException(409, "Save a prediction before revealing this example.")
        else:
            source = body.source
            if body.trace_case >= len(EXERCISES[body.mode]["cases"]):
                raise HTTPException(422, "Choose an available test case.")
            if body.mode == "transfer" and not store.progress(who).get("strings_reviewed"):
                raise HTTPException(409, "Review the string-length prerequisite before this task.")
        try:
            tree = validate_source(source, EXERCISES[body.mode]["entry"] if body.mode in EXERCISES else None)
            if body.mode == "count":
                import ast
                if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"sum", "len"} for node in ast.walk(tree)):
                    raise ValueError("This exercise asks you to practise a loop and counter; do not use sum() or len() for the count.")
            identifier = store.create_run(who, body.mode, source, hashlib.sha256(source.encode()).hexdigest())
        except (ValueError, SyntaxError) as error:
            raise HTTPException(422, str(error)[:300]) from None
        tasks[identifier] = asyncio.create_task(execute_job(who, identifier, body, source))
        tasks[identifier].add_done_callback(lambda task: tasks.pop(identifier, None))
        return {"id": identifier, "status": "queued"}

    @app.get("/api/runs/{identifier}")
    async def get_run(identifier: str, request: Request):
        return owned_run(owner(request), identifier)

    @app.post("/api/runs/{identifier}/cancel")
    async def cancel_run(identifier: str, request: Request):
        who = owner(request, True)
        owned_run(who, identifier)
        store.cancel_run(who, identifier)
        if identifier in tasks:
            tasks[identifier].cancel()
        return {"status": "cancelled"}

    @app.post("/api/hints")
    async def hint(body: HintInput, request: Request):
        who = owner(request, True)
        run = owned_run(who, body.run_id)
        if run["mode"] not in EXERCISES or run["status"] != "complete":
            raise HTTPException(409, "Check a practice attempt before requesting a hint.")
        if body.provider == "local":
            return local_hint(run, store.hint_level(who, body.run_id))
        reserve_cloud(who, body.consent, "attempt hint")
        try:
            answer = await meta.generate("Give one small conceptual hint from the observed failing check. Do not supply a full solution. If all checks pass, invite a fresh independent task.",
                {"task": EXERCISES[run["mode"]]["task"], "source": run["source"], "checks": run["report"]["checks"], "lesson": LESSON["segments"]},
                EXERCISES[run["mode"]]["sources"])
            store.hint_level(who, body.run_id)
            return answer
        except MetaUnavailable as error:
            raise HTTPException(503, str(error)) from None

    @app.post("/api/meta/notes")
    async def meta_notes(body: CloudInput, request: Request):
        who = owner(request, True)
        reserve_cloud(who, body.consent, "lesson notes and image reading")
        try:
            result = await meta.generate("Explain the original lesson's reasoning and the visible code. Label added teaching examples. Cite only the supplied source IDs; do not invent execution results.",
                {"source": LESSON["segments"], "code": COLLECT}, [part["id"] for part in LESSON["segments"]], ROOT / "app" / "media" / "example-code.png")
            store.set_progress(who, "meta_notes", result)
            store.invalidate_packs(who)
            return result
        except MetaUnavailable as error:
            raise HTTPException(503, str(error)) from None

    @app.post("/api/meta/transcribe")
    async def meta_transcribe(body: CloudInput, request: Request):
        who = owner(request, True)
        if not (ROOT / 'app' / 'media' / 'original-lesson.wav').is_file():
            raise HTTPException(409, 'Narration audio is not distributed in this public release. Use the original text sample.')
        reserve_cloud(who, body.consent, "original lesson speech")
        try:
            result = await meta.transcribe(ROOT / "app" / "media" / "original-lesson.wav")
            store.set_progress(who, "meta_transcript", result)
            return result
        except MetaUnavailable as error:
            raise HTTPException(503, str(error)) from None

    @app.post("/api/runs/{identifier}/solution")
    async def solution(identifier: str, request: Request):
        who = owner(request, True)
        run = owned_run(who, identifier)
        if run["mode"] not in EXERCISES or run["status"] != "complete":
            raise HTTPException(409, "Make and check an attempt before requesting the solution.")
        store.mark_solution(who, identifier, run["mode"])
        return {"source": EXERCISES[run["mode"]]["solution"], "label": "Solution viewed — future completion is not recorded as an unaided first attempt."}

    @app.post("/api/packs")
    async def save_pack(body: PackInput, request: Request):
        return store.create_pack(owner(request, True), body.text, SOURCE_HASH)

    @app.post("/api/packs/{identifier}/approve")
    async def approve_pack(identifier: str, body: ReviewInput, request: Request):
        who = owner(request, True)
        pack = store.get_pack(who, identifier)
        latest = store.get_pack(who)
        if not body.reviewed or not pack or pack["source_hash"] != SOURCE_HASH or latest["id"] != identifier:
            raise HTTPException(409, "Review and save the current source version before approving it.")
        return store.approve_pack(who, identifier)

    @app.get("/api/packs/{identifier}/export")
    async def export_pack(identifier: str, request: Request):
        pack = store.get_pack(owner(request), identifier)
        if not pack or not pack["approved"] or pack["source_hash"] != SOURCE_HASH:
            raise HTTPException(409, "Only the current reviewed and approved pack can be exported.")
        content = "<!doctype html><html lang='en'><meta charset='utf-8'><title>LessonTrace student pack</title><style>body{font:17px/1.7 system-ui;max-width:800px;margin:50px auto;padding:20px}pre{white-space:pre-wrap}small{color:#52635a}</style><h1>LessonTrace student pack</h1><small>Original lesson · reviewed version " + str(pack["version"]) + " · source " + SOURCE_HASH[:12] + "</small><pre>" + html.escape(pack["text"]) + "</pre></html>"
        return HTMLResponse(content, headers={"Content-Disposition": f'attachment; filename="lessontrace-student-pack-v{pack["version"]}.html"'})

    @app.delete("/api/my-data")
    async def delete_data(request: Request):
        who = owner(request, True)
        stopping=[]
        for run in store.history(who):
            if run["id"] in tasks:
                stopping.append(tasks[run["id"]])
        stopping.extend(task for identifier,task in list(tasks.items()) if identifier.startswith(('hub:'+who+':','course:'+who+':')))
        for task in stopping:task.cancel()
        await asyncio.gather(*stopping,return_exceptions=True)
        store.delete_owner(who)
        meta.clear_activity(who)
        response = JSONResponse({"deleted": True})
        response.delete_cookie("lessontrace_browser")
        return response

    install_learning_routes(app, owner, store, execution, meta, reserve_cloud, tasks, semaphore)
    install_video_routes(app, owner, store, meta, reserve_cloud)
    coach=LearningCoach(store,meta,tasks)
    app.state.learning_coach=coach
    from .course_service import CourseService,install_course_routes
    course_service=CourseService(store,meta,execution,reserve_cloud,tasks,semaphore,content_root=course_content_root,source_reader=course_source_reader)
    app.state.course_service=course_service
    install_video_learning_routes(app, owner, store, execution, meta, reserve_cloud, tasks, semaphore,coach,course_service)
    install_course_routes(app,owner,course_service)
    coach.hub=install_hub_routes(app, owner, store, execution, meta, reserve_cloud, tasks, semaphore, hub_loader,coach)
    install_coach_routes(app,owner,store,coach)
    from .judge_demo import install_demo_routes
    install_demo_routes(app,owner,store,execution,semaphore,coach)
    return app


app = create_app()
