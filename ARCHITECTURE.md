# How LessonTrace works

1. A versioned base course provides an initial lesson with source anchors. Personal progress is stored in a local SQLite database behind a browser-owned session cookie.
2. Topic and code-completion questions carry concept prerequisites and targets. Code examples and options are executed before acceptance. Conceptual answers still need semantic review; running code alone cannot validate every conceptual claim.
3. The learner predicts, edits, runs and inspects code. CPython runs inside WASI with no host mounts, grants or network host. Each run has a five-second deadline, 256 MiB memory limit, bounded output and an allowlisted syntax/builtin layer.
4. Trace snapshots drive line highlighting, output, frames, objects and loop fingers. The UI distinguishes the line about to run from the line just executed. Trace results belong to the exact source hash and input case.
5. The tutor receives only the consented current question/context. Meta selects from an eligible-action menu. The backend validates the action, source identities, exact short quotes, generated code and an independent Meta claim-support judgement. Rejected teaching does not replace saved work.
6. Python checks and course rules decide progression. Hints, solution views and independent attempts are recorded separately; none is an assessment of lasting mastery.
7. The optional Hub retrieves bounded text/captions from a fixed catalog, compares sources and proposes additional teaching when requested or consented. It uses lexical retrieval, caching and cited passage IDs, not open-ended web browsing or a vector database.

## Trust boundaries

- Untrusted source/model text is rendered as text-based Markdown, not executable HTML.
- Browser code never sees the API key. Mutating requests require the local session's CSRF token. Other browser owners cannot read each other's attempts or model-call metadata.
- The server binds to loopback and trusts only local host names. This is an individual development app, not a hardened public service.
- Meta proposes; backend policy decides whether to run an action; actual Python checks provide execution evidence.
- A second model can also be wrong. Matching an exact quote proves that the quote occurs in a passage, not that it supports every claim. The semantic reviewer reduces some unsupported claims but is not a proof system.
- Test cases are finite. Passing them does not prove general program correctness. Restricted syntax and WASI limits are useful boundaries, not a completed security audit.

## Public Meta request visibility

`GET /api/meta/activity` returns bounded, content-free events for the current browser since the server started. A request is marked LIVE only when the Meta adapter begins its HTTP request without a mock transport. Failures before sending are labelled not sent. The UI displays model, endpoint, purpose, time/status and provider-returned response ID/token counts. It does not publish prompts, code, answers, authorization headers or the operator's key.

The separate explanation-review request appears as its own event. A received response may subsequently fail validation. Actual spend must be checked in Meta Billing; local reservations and reported token usage are not billing receipts.
