# Configuration, privacy and recovery

`scripts/run.py` loads only this repository's `.env`, with existing environment variables taking precedence. It never searches parent projects or reads Windows Credential Manager. `.env.example` contains placeholders only.

| Variable | Default | Effect |
|---|---|---|
| `LESSONTRACE_ENABLE_META` | `0` | `1` explicitly enables live requests; consent is still required in the UI |
| `LESSONTRACE_META_API_KEY` | empty | Your own Meta Model API key, backend only |
| `LESSONTRACE_TEST_LIMIT_CENTS` | `100` | Conservative local request reservations in whole ten-cent steps; maximum 3500 |
| `LESSONTRACE_DATA_DIR` | `.local` | Optional separate local database/cache directory |

A legacy `NOTETAKER_META_API_KEY` environment variable is accepted if the main key variable is absent. The public launcher has no dependency on the old private extension/backend. Never share a local data directory or key between untrusted users.

The local cap records ten cents before an attempted request, including timeouts and rejected responses. Reviewed teaching requires a writer and a reviewer reservation. Raising the configured limit retains previous records; deleting learner data does not reset the usage allowance. This conservative cap is not an exact dollar bill or a provider-enforced spend limit.

Prepared lessons, quizzes, the original sample and Python runs work with Meta disabled. A slow or rejected model request leaves current code and saved progress intact; the UI explains the failure. There are no hidden paid retries. A requested Hub job may take multiple explicitly reserved calls.

Local SQLite data contains attempts, chat, notes, learning preferences and progress. The UI sharing notice describes the material sent to Meta. Under the hackathon/free-credit terms, content may be used for product improvement. Use original/public sample material for the demo. Do not test with children's personal data.

The browser-owned **Delete my local data** action removes that browser's stored attempts/conversation and in-memory call activity; aggregate reservation records remain. Clearing cookies makes a new local identity and does not erase the old database. To start a separate demonstration without changing a real learner's state, use a different `LESSONTRACE_DATA_DIR` and port.

## Startup problems

- **Python warming up:** the first Wasmtime compilation can take a minute. Check `/api/session` for `runner.ready`; do not repeatedly click creation actions.
- **Dependency resolution:** use a fresh Python 3.11 virtual environment and `pip check`. Runtime versions are `wasi-python==0.1.0` and compatible `wasmtime==49.0.0`; do not install a conflicting runtime into a private target directory.
- **Meta unavailable:** verify your key and account access, enable flag, available local reservations and the sharing checkbox. Billing/credits do not automatically enable a restricted payment method.
- **Source unavailable:** YouTube captions or a website can reject the fetch. Use the original sample or a prepared course lesson; the app does not pretend to have read missing screens/audio.
- **Port in use:** select `--port 8898`, then open the matching address. Do not stop unrelated local services.
