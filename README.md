# LessonTrace

**Turn a Python lesson into something you can predict, debug and write yourself.**

LessonTrace combines a source-linked course, optional topic quizzes, an editable Python workspace, step-by-step execution visualisation, and a bounded Meta tutor. It helps learners move from understanding an explanation to attempting a program. This prototype does not claim measured learning gains or certify mastery.

![Original prepared sample with an editable program, actual execution state and all three coding checks passed](docs/screenshots/original-sample.jpg)

This is the standalone **2026 Meta Global AI Developer Hackathon** submission. The older private note-capture extension and early planning are not included or required. The author confirms that all standalone website code was created on or after **October 26, 2026**. See [event provenance](PROVENANCE.md).

## Run it

Tested on Windows with **64-bit Python 3.11**. The Python runtime is downloaded from public PyPI; no Docker, private repository, paid deployment or Node build is required to run the app. Allow roughly 200 MB for the first dependency download and extra time for the first runtime compilation.

```powershell
git clone https://github.com/nikhil5562/LessonTrace-Hackathon.git
cd LessonTrace-Hackathon
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts/run.py
```

Open **http://127.0.0.1:8897/#courses**. Wait for **Python ready** before opening a lesson. If that port is in use, run `scripts/run.py --port 8898` and use the matching address. Keep the app bound to this computer; this prototype is not a multi-user hosted service.

On macOS/Linux, the equivalent commands use `python3.11 -m venv .venv`, `.venv/bin/python` and `cp .env.example .env`. This release was verified on Windows; other operating systems have not been acceptance-tested.

### No key needed for the first run

On the course page choose **Open sample →** under **Try the original sample**. Its source, notes and loop examples are original prepared material, explicitly labelled **ORIGINAL DEMO · PREPARED**. Predict what the code prints, inspect the real Python trace, then debug the extra outer `break`. Opening this sample does not grant course prerequisites.

The 24 prepared course lessons also run without a key: read → topic/debug questions → coding checks → next eligible concept. Quizzes can be skipped to inspect the editor; passing the required checks is still necessary to unlock a new course concept. No-key operation is not represented as fresh Meta inference.

### Enable live Meta tutoring with your own key

Edit the local `.env` copied above:

```dotenv
LESSONTRACE_ENABLE_META=1
LESSONTRACE_META_API_KEY=your_own_meta_model_api_key
LESSONTRACE_TEST_LIMIT_CENTS=100
```

Restart the server. In a lesson, choose **Ask Meta**, review the consent text and check the sharing box, then ask a question or request a hint. Open **Live Meta calls** before sending to see the writer and separate explanation-review requests. The UI shows the actual endpoint, model, request status and returned response ID/token counts when supplied. Mock transports are labelled **CONTROLLED TEST**; validation failures before HTTP are **NO HTTP REQUEST SENT**. A response receipt is not evidence of correctness.

The key is read only by the backend from this project's explicit `.env` or environment. It is never sent to browser JavaScript. No shared key, judge login or access code is needed. `.env` is ignored by Git. Never put a real key in `.env.example`, a screenshot or the public video.

The default local allowance reserves **US$0.10 per attempted model request**, including failed requests. A reviewed tutor reply usually needs **two requests**. This is an intentionally conservative local stop, **not an estimate of Meta's actual bill**. Provider-reported tokens and actual dollar billing are different things. A fresh judge installation starts with its own ledger. Restarting preserves reservations. See [configuration and privacy](CONFIGURATION.md).

## What Meta does

All runtime cloud inference in this submission uses **Meta models**. There is no Google/OpenAI/Anthropic inference fallback.

| Feature | Real work performed | Implementation |
|---|---|---|
| Tutor | Chooses among backend-permitted teaching actions; explains the learner's question, source passages and selected actual execution state | [`video_learning.py`](server/lessontrace_site/video_learning.py), [`adaptive.py`](server/lessontrace_site/adaptive.py) |
| Independent explanation review | A separate Muse Spark request judges source/claim support before anchored teaching is accepted | [`claim_review.py`](server/lessontrace_site/claim_review.py), [`provider_audit.py`](server/lessontrace_site/provider_audit.py) |
| Lesson Hub | Reads bounded passages from a curated topic catalog, proposes a learning path and prepares additional original teaching | [`hub.py`](server/lessontrace_site/hub.py), [`hub_sources.py`](server/lessontrace_site/hub_sources.py) |
| Course preparation | Reusable, versioned Meta-authored base lessons; opening a saved lesson replays it rather than regenerating it | [`course_service.py`](server/lessontrace_site/course_service.py), [`course_content/`](course_content/) |
| Video import | Creates original notes/practice from available captions for a learner-supplied YouTube URL | [`video_lessons.py`](server/lessontrace_site/video_lessons.py) |

The teaching/review model is **`muse-spark-1.3`** through **`POST https://api.meta.ai/v1/chat/completions`**, implemented in [`meta.py`](server/lessontrace_site/meta.py). The source includes a legacy Meta speech adapter with a controlled wire test; the public sample contains no narration recording and speech is not part of the submitted demonstration. No Meta image-generation model is called. Execution diagrams are drawn from actual Python trace data.

## More than a retrieval chatbot

The learning loop is **read → predict → execute → inspect → debug → retry → unlock**. The backend tracks concept prerequisites and actual code checks. The model can suggest an allowed action; it cannot award a pass, invent a successful execution, remove prerequisites or silently change the original lesson. The Python runner checks the program.

The agent is bounded and event-driven, not an unrestricted background assistant. It uses current lesson state, recorded attempts, preferences and permitted actions. Extra research requires consent, waits for the learner and has a nudge cap. The Hub supplements the course after difficulty; it does not replace the initial lesson with endless extra tasks.

Retrieval is a **small, lexical, source-ID-based system** over supplied/cached passages. It is not an embedding database or a search of all YouTube. Exact quoted anchors, actual execution checks, separate semantic review and prerequisite rules reduce several failure modes; none eliminates hallucination. See [architecture](ARCHITECTURE.md) and [verification design](CLAIM_REVIEW.md).

## Verify the release

```powershell
$env:PYTHONPATH='server'
.\.venv\Scripts\python.exe -m pytest server/tests -q
```

Browser-flow tests additionally need Node and the optional test dependency:

```powershell
npm install --prefix .local/frontend-check jsdom@26.1.0
.\.venv\Scripts\python.exe -m pytest server/tests -q
```

Tests use controlled model responses and **real bounded Python**. They do not consume Meta credits. See [the release checks and honest limits](VALIDATION.md), [historical evaluation](EVALUATION.md) and [a three-minute demo outline](DEMO.md). The bundled editor is reproducible with `npm ci --prefix editor` followed by `node editor/build.mjs`.

A separate [recorded original-sample run](evaluation/live-original-2026-11-03.json) contains an accepted **live Muse Spark tutor reply plus its independent review**, provider-returned response IDs, original input/question and real failing/corrected Python traces. It is recorded evidence, not a live replay or a substitute for showing fresh API calls in the demo video.

## Rights and scope

Our application code is **MIT licensed**. Third-party material retains its own terms. Course files containing CS50 anchors have a separate **CC BY-NC-SA 4.0** content licence; Python documentation and editor/runtime dependencies have separate notices. These assets are **not** all MIT. See [content licensing](CONTENT_LICENSE.md), [third-party notices](THIRD_PARTY_NOTICES.md), and [licence texts](licenses/).

No tutorial footage, full caption downloads, book PDFs, private learner data, private Git history or credentials are distributed. The original demonstration can be recorded entirely from our own source and UI. No external video clips are needed. For importing other material, use content you have permission to process; do not redistribute source recordings simply because a URL is public.

Hosting is optional for the submitted workflow. The author still needs to record and host the <=3-minute demo video and complete the hackathon submission form. This repository does not claim organizer endorsement or a ruling that it qualifies beyond the anti-project list.
