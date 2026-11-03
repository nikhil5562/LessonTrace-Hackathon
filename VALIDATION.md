# Release validation — November 3, 2026

## Standalone environment

Checked in a new, separate project environment on Windows using Python 3.11, `wasi-python==0.1.0` and compatible `wasmtime==49.0.0`. Dependencies were obtained from public PyPI; the runtime wheels were downloaded from the public index, installed without a private runtime directory, and `pip check` reported **no broken requirements**. `constraints.txt` records the resolved environment. No Docker or private extension/backend is needed.

The runtime passed its first cold startup. The browser editor was rebuilt from `editor/package-lock.json` using public npm dependencies; its SHA-256 was byte-identical to the distributed bundle (`7e4d91ae722bdda61aaa5e13f7d6dc906778132fba4bbe4b382accfc29efcbc3`).

A fresh Git checkout preserved every v1/v2 frozen lesson hash and passed four original-demo/request-activity tests in 24.82 seconds, including a cold runtime cache. That checkout used the already verified release dependency environment; it did not import the private project's source or state. Its test data and runtime cache were created inside that checkout.

## Automated and execution checks

- **315 tests passed**, zero skipped, in **179.04 seconds** with Node/jsdom installed. These exercise real bounded Python and controlled model I/O. One upstream Starlette TestClient deprecation warning remains; it is not a failed test.
- The first packaging run had 313 passes and one missing documentation-file failure. The file/route was corrected; the final full run passed. The public documentation route received a further focused passing check after its allowlist cleanup.
- All **24 frozen course lessons** completed proposal-execution receipt preparation using the independently installed runner, without a Meta request. This is an execution replay, not a new semantic review or proof that every explanation is correct.
- The original demo's deliberate extra outer `break` fails; its corrected function passes three inputs, including empty rows. Starting/passing this sample does not grant course prerequisites or overwrite the active course session.
- Cross-browser ownership, CSRF, stale source state, bounded execution, quote checks, review failures, request reservations, progression and safe Markdown are covered by the suite. Test transports never appear as live calls.

## One new live-provider check

An original-sample tutoring request and a separate claim-support review both received real **Muse Spark 1.3** responses. The tutor reply was accepted. It identified the reached outer-body break using the observed trace. Python confirmed the failing starter and the corrected three-case pass.

The [recorded evidence](evaluation/live-original-2026-11-03.json) includes original source/question/code, actual model reply, returned response IDs/token counts and execution traces. Two requests reserved US$0.20 against the existing operator allowance; no bulk content regeneration or semantic batch was performed. Reservation amounts are not actual billed charges. No key or private account/learner data is included in the published evidence.

This check used the application's HTTP endpoints in a local test client and the real Meta HTTP adapter. It was separate from the later native-UI screen recording described below.

## Native interface inspection

Opened the isolated release on port 8898 with separate sample data. Checked the course page, original sample launch, both quiz questions, transition to the editor, failing starter, edited solution, three-case pass, step navigation, returned value, names/objects and boxes/fingers. Inspected both the narrow in-app-browser layout and a 1280-pixel desktop layout. The screenshot in the README is the actual corrected original-sample run, with prepared notes explicitly labelled.

## Recorded native-UI demo

The completed English-narrated demo is **173.978 seconds** (under three minutes), 1920×1080, with H.264 video and AAC audio. Its opening highlights bounded Meta teaching/research agents and the October 26 event build date. It shows original prepared notes, prediction, a deliberately failing program, actual Python trace visualisation, live Muse Spark tutoring plus separate review, and edited code passing three checks, including empty rows.

Two accepted tutoring takes produced **four real Meta requests**, separate from the earlier test-client check. The final cut uses the closer second take. [Matching recorded evidence](evaluation/demo-video-2026-11-03.json) retains source code, model replies, all four request receipts, actual Python run reports, the video SHA-256 and editing disclosures. Video production made no additional Meta requests. API waiting is accelerated where labelled; result frames pause for explanation. The Hub segment shows its setup, not a new research run.

The full movie decoded without errors. All **39 caption cues** are within the movie and do not overlap. Audio is present (mean −16.9 dB; peak −1.4 dB). The final video was [uploaded to YouTube as unlisted](https://youtu.be/IScnLEqgUWI) on November 3, 2026. YouTube reported no copyright issues, and playback was observed while signed out (12 seconds into the 2:54 video). The hackathon entry was submitted on November 3, 2026 under Indie Developer / Build for Your World; the saved entry reopened as "Your Submission" with the submitted details. These checks establish media integrity and recorded behavior, not student learning gains, judging success or organizer approval.

## Publication checks and limits

The publication process checks exact frozen-content hashes, bundled editor hash, ignored local data, private path/credential patterns and actual known key literals before pushing. A fresh public repository is used; private Git history and the older capture project are not exported.

This is a development prototype, not an independently security-audited hosted service. Tests are finite; no student learning study or independent teacher approval has been performed. Windows was tested; other operating systems were not acceptance-tested. Historical model evaluation is small, with a known false block. Licensing differs between original code, prepared course content and dependencies; see the licence notices before reuse.
