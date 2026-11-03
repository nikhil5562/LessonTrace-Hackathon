"""Run actual UI startup/click handlers with synthetic API responses, without a browser."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from test_video_learning import lesson, SyntheticMeta
from lessontrace_site.main import create_app
from lessontrace_site.adaptive import unit_state
from lessontrace_site.video_learning import blank_progress, public_state
from lessontrace_site.video_lessons import public_session

ROOT = Path(__file__).resolve().parents[2]


class ReadyRunner:
    ready = True
    error = None

    async def warmup(self):
        pass

    async def close(self):
        pass


def record(identifier):
    spec = lesson("video-fixture")
    spec["units"][0]["prediction"].update(answer_index=1, verification={"output": "91", "runtime": "Synthetic UI fixture"})
    return {
        "lesson_id": identifier, "interactive": True, "title": "Synthetic UI lesson",
        "answer": spec["answer"], "sources": ["video-fixture"], "curriculum": spec,
        "video_id": "4t10v2QmTHU", "url": "https://www.youtube.com/watch?v=4t10v2QmTHU",
        "caption_source": "Synthetic test captions", "language": "en", "auto_generated": False,
        "caption_chunks": [{"id": "video-fixture", "start": 0, "end": 20, "text": "Synthetic key-value example."}],
        "created": 1, "coverage": "Synthetic UI fixture", "model": "synthetic-test-model",
        "practice_basis": "Synthetic test exercises",
    }


@pytest.mark.parametrize("scenario", [
    "empty", "existing", "workspace_failure", "saved_lesson_failure",
    "offline_reconnect", "creation_failure", "studio_missing", "edited_url", "quoted_quiz",
])
def test_creation_readiness_and_click_recover_independently_of_saved_preview(tmp_path, scenario):
    node = os.environ.get("LESSONTRACE_NODE") or shutil.which("node")
    jsdom = ROOT / ".local/frontend-check/node_modules/jsdom/lib/api.js"
    if not node or not jsdom.is_file():
        pytest.skip("Frontend startup checks require Node and the optional jsdom 26.1.0 setup in scripts/README.md")
    provider = SyntheticMeta()
    app = create_app(tmp_path, runner=ReadyRunner(), provider=provider)
    with TestClient(app) as client:
        routes = ["/api/session", "/api/lesson", "/api/progress", "/api/learning", "/api/learning/functions", "/api/coach"]
        responses = {}
        for route in routes:
            response = client.get(route)
            assert response.status_code == 200, response.text
            responses[route] = response.json()
    responses["/media/timing.json"] = []
    old = record("1" * 32)
    if scenario == "quoted_quiz":
        old["curriculum"]["units"][0]["quiz"] = [{
            "kind": "concept", "prompt": "Which item does friends[2] refer to?",
            "code": 'friends = ["Paul", \'Dana\', "Nathan"]',
            "options": ["The second item", "The third item", "The whole list"],
            "answer_index": 1, "expected_output": "",
            "explanation": "Index two identifies the third item.", "sources": ["video-fixture"],
        }]
    old_progress = blank_progress(old)
    if scenario == "existing":
        state = unit_state(old_progress, "lookup")
        state["phase"] = "exercise"
        state["quiz_skipped"] = True
    new = copy.deepcopy(old)
    new["lesson_id"] = "2" * 32
    payload = {
        "scenario": scenario, "responses": responses,
        "initial_session": None if scenario == "empty" else public_session(old),
        "initial_learning": None if scenario == "empty" else public_state(old, old_progress),
        "created": {
            "session": public_session(new), "learning": public_state(new, blank_progress(new)),
            "allowance": responses["/api/session"]["meta"]["allowance"],
        },
    }
    result = subprocess.run(
        [node, str(Path(__file__).with_name("video_startup.mjs")), str(ROOT), str(jsdom)],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert provider.calls == [], "UI startup tests must never generate live content"
