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

This check used the application's HTTP endpoints in a local test client and the real Meta HTTP adapter. It was not a screen recording of a native live-tutor interaction. The final demo video must still show fresh live calls in the actual UI.

## Native interface inspection

Opened the isolated release on port 8898 with separate sample data. Checked the course page, original sample launch, both quiz questions, transition to the editor, failing starter, edited solution, three-case pass, step navigation, returned value, names/objects and boxes/fingers. Inspected both the narrow in-app-browser layout and a 1280-pixel desktop layout. The screenshot in the README is the actual corrected original-sample run, with prepared notes explicitly labelled.

## Publication checks and limits

The publication process checks exact frozen-content hashes, bundled editor hash, ignored local data, private path/credential patterns and actual known key literals before pushing. A fresh public repository is used; private Git history and the older capture project are not exported.

This is a development prototype, not an independently security-audited hosted service. Tests are finite; no student learning study or independent teacher approval has been performed. Windows was tested; other operating systems were not acceptance-tested. Historical model evaluation is small, with a known false block. Licensing differs between original code, prepared course content and dependencies; see the licence notices before reuse.
