# Evaluation evidence

## Historical development evidence

The JSON files in `evaluation/` retain development outcomes and fixture identities. They are not a new live-provider run of this public checkout. Private allowance totals and QA identifiers were removed with an explicit publication note.

- `scenarios.json` and `results-2026-10-31.json`: scripted learner/retrieval scenarios with per-case results and limits.
- `adversarial-v1.json` and `claim-review-full-2026-11-03.json`: 22 semantic-review cases, 21 expected decisions, one false block; 14/14 unsupported claims rejected and 7/8 supported claims accepted. Zero unavailable cases in that run.
- `claim-review-results-2026-11-02.json` and `claim-review-followup-2026-11-02.json`: earlier bounded subsets and follow-up, not additional independent samples to aggregate into a larger success claim.
- `rubric-oracles-2026-11-02.json`: 24 reference programs and 24 common-error mutants under independent topic oracles.
- `course-audit-summary-2026-11-03.json`: 24 frozen lessons supported across an expanded-source run and focused follow-up, with limitations and errata.

## Current release evidence

See [VALIDATION.md](VALIDATION.md) for checks performed on this standalone public candidate. Tests use actual local Python but controlled model replies, unless a result is explicitly labelled live. There are no student participants, measured retention gains or teacher endorsements in these results.

`live-original-2026-11-03.json` is a new, separately labelled live-provider check of the original sample: two real Muse Spark requests (tutoring plus separate review), both received, tutoring accepted, deliberate bug failed and corrected code passed three actual Python cases. It includes original source/code/question, model reply, returned response IDs and execution receipts. Private budget/account material was excluded. It is not footage of the native browser session.

`scripts/review_frozen_course.py` can reproduce the proposal-execution preparation without a key. `--live` explicitly enables paid semantic audit requests with your own key and local cap; ordinary tests never enable it. Large regeneration/audit runs are not part of the default setup.
