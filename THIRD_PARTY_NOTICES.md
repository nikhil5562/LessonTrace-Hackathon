# Third-party notices

- **CS50 / Harvard / David J. Malan:** short evidence anchors in prepared course content. CC BY-NC-SA 4.0; attribution, change statement and scope in [CONTENT_LICENSE.md](CONTENT_LICENSE.md). No CS50 recording is bundled.
- **Python Software Foundation:** Python documentation anchors and CPython runtime. PSF License v2 and related notices; documentation example code additionally 0BSD where stated by the PSF. [Official licensing](https://docs.python.org/3/license.html); [included text](licenses/PSF-PYTHON-LICENSE.txt).
- **CodeMirror, Lezer and related editor packages:** MIT and retained author notices, collected verbatim in [EDITOR_NOTICES.md](licenses/EDITOR_NOTICES.md). Exact versions are in `editor/package-lock.json`. The distributed browser bundle was rebuilt from that lockfile.
- **wasi-python 0.1.0:** runtime downloaded from public PyPI, not copied from a private project. Apache-2.0 package with bundled component notices; CPython retains its separate PSF licence. Inspect installed package licence/NOTICE metadata when redistributing the runtime. The wheel itself is not committed.
- **Wasmtime 49.0.0 / Bytecode Alliance:** Apache-2.0 with LLVM exception, obtained as a public dependency. [Included upstream licence](licenses/WASMTIME-LICENSE.txt); the binary is not committed.
- **Meta model API:** externally accessed service, not a vendored model. Use is subject to the Meta Model API terms, acceptable-use/geographic policy and applicable account/credit terms. No Meta key is distributed. No Meta/Harvard/CodeSignal/Python Tutor endorsement is implied.

Other Python and development dependencies are downloaded by their public package names; their installed licence metadata remains authoritative. Our root MIT licence does not override upstream conditions.
