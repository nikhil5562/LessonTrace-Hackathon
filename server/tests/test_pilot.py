import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

import pytest
import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from lessontrace_site.content import COLLECT, COUNT_SOLUTION, REFERENCES
from lessontrace_site.guest import Unsupported, validate
from lessontrace_site.hints import local_hint
from lessontrace_site.main import create_app
from lessontrace_site.meta import MetaProvider, MetaUnavailable
from lessontrace_site.runner import WasiRunner
from lessontrace_site.store import Store


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    runner = WasiRunner(tmp_path_factory.mktemp("wasi"))
    # Use the already compiled cache; it is never granted to the guest.
    runner.cache = ROOT / ".local" / "wasi-cache"
    asyncio.run(runner.warmup())
    assert runner.ready, runner.error
    yield runner
    asyncio.run(runner.close())


def execute(runtime, source, entry=None, args=None):
    return asyncio.run(runtime.execute({"source": source, "entry": entry, "arguments": args or [[]], "trace_case": 0}))


def test_actual_list_execution_and_after_line_state(runtime):
    result = execute(runtime, COLLECT, "collect_heavy_rain", [[[5, 22, 20, 45]]])
    assert result["cases"][0]["actual"] == [22, 45]
    assert result["source_sha256"] == hashlib.sha256(COLLECT.encode()).hexdigest()
    trace = result["cases"][0]["events"]
    appended = [event for event in trace if event["line"] == 5]
    assert len(appended) == 2
    first_heavy = appended[0]["frames"][-1]["bindings"]["heavy"]["object_id"]
    assert appended[0]["objects"][first_heavy]["items"] == [{"kind": "scalar", "value": 22}]
    assert appended[1]["frames"][-1]["bindings"]["heavy"]["object_id"] == first_heavy
    final = trace[-1]
    assert final["kind"] == "return"
    assert final["frames"][-1]["bindings"]["mm"]["value"] == 45
    assert any(loop["exhausted"] for loop in final["loops"])


def test_alias_rebinding_and_mutation_are_distinct(runtime):
    result = execute(runtime, REFERENCES)
    case = result["cases"][0]
    assert case["output"] == "[9, 9, 0] [1, 2] [9, 9, 0]\n"
    final = case["events"][-1]
    values = final["frames"][-1]["bindings"]
    assert values["a"]["object_id"] == values["c"]["object_id"]
    assert values["b"]["object_id"] != values["a"]["object_id"]


def test_equal_lists_do_not_merge(runtime):
    result = execute(runtime, "a = [1]\nb = [1]\na.append(2)\n")
    values = result["cases"][0]["events"][-1]["frames"][-1]["bindings"]
    assert values["a"]["object_id"] != values["b"]["object_id"]


def test_printing_does_not_become_a_return(runtime):
    result = execute(runtime, "def count_heavy(rainfall):\n    print(2)\n", "count_heavy", [[[22, 45]]])
    assert result["cases"][0]["actual"] is None
    assert result["cases"][0]["output"] == "2\n"


def test_empty_and_threshold_inputs(runtime):
    result = execute(runtime, COUNT_SOLUTION, "count_heavy", [[[]], [[20]], [[21, 21]]])
    assert [case["actual"] for case in result["cases"]] == [0, 0, 2]


def test_infinite_loop_stops_with_observed_limit(runtime):
    result = execute(runtime, "def count_heavy(rainfall):\n    while True:\n        pass\n", "count_heavy", [[[21]]])
    assert result["cases"][0]["error"]["type"] == "LimitReached"


@pytest.mark.parametrize("source", ["import os", "x = (1).__class__", "open('private')", "def f(x):\n    return x ** 999999\n"])
def test_unsupported_access_rejected_before_execution(source):
    with pytest.raises(Unsupported):
        validate(source, None)


def test_targeted_hint_uses_boundary_failure():
    run = {"source": COUNT_SOLUTION.replace("> 20", ">= 20"), "report": {"checks": [{"input": [20], "actual": 1, "expected": 0, "passed": False}]}}
    hint = local_hint(run, 1)
    assert hint["line"] == 4 and hint["basis"]["input"] == [20]
    assert "threshold" in hint["text"]


@pytest.fixture
def client(runtime, tmp_path):
    execution = WasiRunner(tmp_path)
    execution.cache = ROOT / ".local" / "wasi-cache"
    app = create_app(tmp_path, runner=execution)
    with TestClient(app) as browser:
        session = browser.get("/api/session").json()
        browser.headers["X-LessonTrace-CSRF"] = session["csrf"]
        for _ in range(100):
            if browser.get("/api/session").json()["runner"]["ready"]:
                break
            time.sleep(.02)
        yield browser


def test_csrf_prediction_gate_and_no_secret_routes(client):
    assert client.post("/api/runs", json={"mode": "example"}).status_code == 409
    assert client.post("/api/prediction", json={"text": "[22,45]"}, headers={"X-LessonTrace-CSRF": "wrong"}).status_code == 403
    assert client.get("/.local/lessontrace.sqlite3").status_code == 404
    assert client.get("/plan/.local/lessontrace.sqlite3").status_code == 404
    assert client.get('/plan/').status_code==200
    assert client.get('/plan/CLAIM_REVIEW.md').status_code==200
    for name in ('adversarial-v1.json','claim-review-results-2026-11-02.json','claim-review-followup-2026-11-02.json','rubric-oracles-2026-11-02.json','claim-review-full-2026-11-03.json','course-audit-summary-2026-11-03.json'):
        assert client.get('/plan/evaluation/'+name).status_code==200
    for path in ('/plan/evaluation/unknown.json','/plan/server/lessontrace_site/course_rubrics.py','/plan/course_content/python-fundamentals-v2/variables.json'):
        assert client.get(path).status_code==404
    assert client.get("/api/session").json()["meta"]["enabled"] is False


def test_pack_edit_invalidates_approval_and_is_private(client):
    pack = client.post("/api/packs", json={"text": "Reviewed notes about loops and returns."}).json()
    assert client.get(f"/api/packs/{pack['id']}/export").status_code == 409
    assert client.post(f"/api/packs/{pack['id']}/approve", json={"reviewed": True}).status_code == 200
    assert client.get(f"/api/packs/{pack['id']}/export").status_code == 200
    client.post("/api/packs", json={"text": "A changed lesson pack needs a new review."})
    assert client.get(f"/api/packs/{pack['id']}/export").status_code == 409
    # Another browser cannot approve or export this browser's private version.
    old = client.cookies.get("lessontrace_browser")
    client.cookies.clear()
    other = client.get("/api/session").json()
    client.headers["X-LessonTrace-CSRF"] = other["csrf"]
    assert client.get(f"/api/packs/{pack['id']}/export").status_code == 409
    assert client.cookies.get("lessontrace_browser") != old


def test_transfer_requires_reviewed_prerequisite(client):
    response = client.post("/api/runs", json={"mode": "transfer", "source": "def collect_long_names(names):\n    return []\n"})
    assert response.status_code == 409


def test_meta_paused_never_touches_transport():
    async def check():
        with pytest.raises(MetaUnavailable, match="paused"):
            await MetaProvider(enabled=False, key="test-not-a-real-key").generate("Explain", {}, ["source-1"])
    asyncio.run(check())


def test_actual_api_attempt_checks_and_owner_isolation(client):
    started = client.post("/api/runs", json={"mode": "count", "source": COUNT_SOLUTION}).json()
    for _ in range(100):
        result = client.get("/api/runs/" + started["id"]).json()
        if result["status"] in {"complete", "failed"}:
            break
        time.sleep(.02)
    assert result["status"] == "complete", result
    assert result["report"]["all_passed"] is True
    assert len(result["report"]["checks"]) == 6
    client.cookies.clear()
    client.get("/api/session")
    assert client.get("/api/runs/" + started["id"]).status_code == 404


def test_meta_routes_are_paused_before_reserving_or_sending(client):
    assert client.post("/api/meta/notes", json={"consent": True}).status_code == 409
    assert client.post("/api/meta/transcribe", json={"consent": True}).status_code == 409
    with client.app.state.store.db() as db:
        assert db.execute("SELECT count(*) FROM provider_reservations").fetchone()[0] == 0


def test_meta_wire_output_and_citation_validation():
    def responder(request):
        sent = json.loads(request.content)
        assert sent["model"] == "muse-spark-1.3"
        assert request.headers["Authorization"] == "Bearer synthetic-test-key"
        return httpx.Response(200, json={"id": "mock-response", "model": "muse-spark-1.3", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"answer": "Inspect the boundary case.", "sources": ["source-3"]})}}]})
    async def check():
        provider = MetaProvider(enabled=True, key="synthetic-test-key", transport=httpx.MockTransport(responder))
        result = await provider.generate("Give one hint", {"actual": 1, "expected": 0}, ["source-3"])
        assert result["provider"] == "meta" and result["sources"] == ["source-3"]
    asyncio.run(check())


def test_meta_fabricated_source_is_rejected():
    def responder(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"answer": "Unsupported", "sources": ["nonexistent-source"]})}}]})
    async def check():
        provider = MetaProvider(enabled=True, key="synthetic-test-key", transport=httpx.MockTransport(responder))
        with pytest.raises(MetaUnavailable):
            await provider.generate("Explain", {}, ["source-3"])
    asyncio.run(check())


def test_wasi_cannot_read_a_host_file(runtime, tmp_path):
    sentinel = tmp_path / "host-only.txt"
    sentinel.write_text("private-test-sentinel")
    code = "try:\n open(" + repr(str(sentinel)) + ").read()\n print('unexpected-access')\nexcept OSError:\n print('host-file-denied')\n"
    result = asyncio.run(runtime.call(code))
    assert result.stdout.strip() == b"host-file-denied"


def test_wasi_has_no_network_socket_access(runtime):
    code = "try:\n import socket\n connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n connection.connect(('127.0.0.1', 8765))\n print('unexpected-network')\nexcept (ImportError, OSError, AttributeError):\n print('network-denied')\n"
    result = asyncio.run(runtime.call(code))
    assert result.stdout.strip() == b"network-denied", (result.exit_code, result.stderr, result.trapped)


def test_wasi_memory_bound(runtime):
    result = asyncio.run(runtime.call("data = bytearray(400 * 1024 * 1024)\nprint('unexpected-allocation')"))
    assert result.exit_code != 0 or result.trapped
    assert b"unexpected-allocation" not in result.stdout


def test_cancelled_job_cannot_overwrite_cancelled_state(tmp_path):
    class SlowRunner:
        ready, error = True, None
        async def warmup(self):
            pass
        async def execute(self, payload):
            await asyncio.sleep(10)
            raise AssertionError("Cancelled work must not complete")
        async def close(self):
            pass
    app = create_app(tmp_path, runner=SlowRunner())
    with TestClient(app) as browser:
        browser.headers["X-LessonTrace-CSRF"] = browser.get("/api/session").json()["csrf"]
        started = browser.post("/api/runs", json={"mode": "count", "source": COUNT_SOLUTION}).json()
        assert browser.post("/api/runs/" + started["id"] + "/cancel", json={}).status_code == 200
        assert browser.get("/api/runs/" + started["id"]).json()["status"] == "cancelled"


def test_actual_wasi_deadline(runtime):
    result = asyncio.run(runtime.call("while True: pass"))
    assert result.trapped == "deadline"


def test_actual_wasi_cancellation_releases_the_runner(runtime):
    async def check():
        task = asyncio.create_task(runtime.call("while True: pass"))
        await asyncio.sleep(.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        after = await runtime.call("print('runner-released')")
        assert after.stdout.strip() == b"runner-released"
    asyncio.run(check())


def test_hint_chooses_small_boundary_case():
    run = {"source": COUNT_SOLUTION.replace("> 20", ">= 20"), "report": {"checks": [
        {"input": [5,22,20,45], "actual": 3, "expected": 2, "passed": False},
        {"input": [20], "actual": 1, "expected": 0, "passed": False}]}}
    assert local_hint(run, 1)["basis"]["input"] == [20]


def test_meta_speech_wire_uses_original_audio_and_honest_timing(tmp_path):
    audio = tmp_path / "original.wav"
    audio.write_bytes(b"RIFF-synthetic-test-audio")
    def responder(request):
        assert request.url.path == "/v1/asr/transcribe"
        assert b"ENDPOINTING" in request.content
        assert b"muse-voice-transcribe-1.0" in request.content
        return httpx.Response(200, json={"transcript": "Original lesson", "turns": [{"startMs":0,"endMs":1000,"transcript":"Original lesson"}]})
    async def check():
        provider = MetaProvider(enabled=True, key="synthetic-test-key", transport=httpx.MockTransport(responder))
        result = await provider.transcribe(audio)
        assert result["transcript"] == "Original lesson" and "not word timestamps" in result["timing"]
    asyncio.run(check())


def test_repeated_calls_have_distinct_frame_identity(runtime):
    source = "def helper(x):\n    return x + 1\ndef collect_heavy_rain(rainfall):\n    a = helper(1)\n    b = helper(2)\n    return [a, b]\n"
    result = execute(runtime, source, "collect_heavy_rain", [[[5]]])
    assert result["cases"][0]["actual"] == [2, 3]
    frames = {frame["id"] for event in result["cases"][0]["events"] for frame in event["frames"] if frame["name"] == "helper"}
    assert len(frames) == 2


def test_provider_budget_includes_earlier_approved_test_reservations(tmp_path):
    legacy = tmp_path / "old-ledger.json"
    legacy.write_text(json.dumps({"reserved_micro_usd": 900000}))
    store = Store(tmp_path / "pilot.sqlite3", legacy)
    store.reserve_provider("test-owner", "synthetic test")
    with pytest.raises(ValueError, match="limit"):
        store.reserve_provider("test-owner", "another test")


@pytest.mark.parametrize('approved_total',[120,1500,2000,2500,3500])
def test_explicit_budget_increase_keeps_all_existing_reservations(tmp_path,approved_total):
    legacy=tmp_path/'old-ledger.json'
    legacy.write_text(json.dumps({'reserved_micro_usd':900000}),encoding='utf-8')
    path=tmp_path/'pilot.sqlite3'
    original=Store(path,legacy)
    original.reserve_provider('test-owner','First approved reservation')
    expanded=Store(path,legacy,provider_limit_cents=approved_total)
    remaining=(approved_total-100)//10
    assert expanded.provider_allowance()['remaining_requests']==remaining
    for index in range(remaining):expanded.reserve_provider('test-owner','New approved request '+str(index))
    with pytest.raises(ValueError,match='limit'):expanded.reserve_provider('test-owner','Not approved')
    assert expanded.provider_allowance()['reserved_cents']==approved_total
    assert Store(path,legacy).provider_allowance()['remaining_requests']==0


@pytest.mark.parametrize('limit',[0,15,-100,True,1001,3510,'120'])
def test_invalid_testing_limits_fail_closed(tmp_path,limit):
    with pytest.raises(ValueError):Store(tmp_path/'pilot.sqlite3',provider_limit_cents=limit)
