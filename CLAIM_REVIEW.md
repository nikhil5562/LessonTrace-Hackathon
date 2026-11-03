# Verification and hallucination reduction

The model does not decide that a program passed. Actual CPython execution checks the expected output/return, input preservation and trace. Backend concept rules control course progression.

Anchored generated teaching is checked in layers:

1. JSON/schema and permitted action validation.
2. Source IDs must be supplied; each cited short quote must occur word for word in the corresponding passage.
3. Generated examples, completion choices, references and deliberate bugs are run with bounded Python. A debug task must reproduce its bug and its corrected program must pass its cases.
4. A separate Muse Spark request receives the claim/source context and execution receipts. It reviews semantic support and, for course content, coverage against independently specified reference rubrics.
5. Backend-selected literal excerpts constrain coverage receipts; the model cannot invent a different excerpt or award course completion.

These checks can block valid explanations as well as bad ones. The published 22-case historical semantic challenge accepted seven of eight supported cases, rejected fourteen of fourteen unsupported cases and had one false block. It is a small development set, not a held-out benchmark or proof that other hallucinations cannot pass. See `evaluation/claim-review-full-2026-11-03.json`.

Course rubrics/oracles were operator/Codex assisted, not approved by an independent teacher. An automated expanded-source audit supported all 24 lessons across an initial run and targeted follow-up; it was not a single uniform independent benchmark. Frozen content and hash-bound errata remain inspectable. Local release tests exercise enforcement contracts using controlled responses, not fresh semantic inference.
