import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ouroboros.core.types import Result
from ouroboros.gui.harness import Harness
from ouroboros.gui.readiness_preview import generate_preview


def payload(**kw):
    return dict(
        goal="Show tasks",
        acceptance_criteria=["Opening shows the task list"],
        constraints=[],
        decision="preview",
        reason="A visible result is possible",
        evidence=["Show tasks"],
        assumptions=["Text list"],
        required_decisions=[],
        scenes=[
            {
                "user_action": "Open",
                "visible_result": "Task list",
                "failure_alternative": "Show unavailable",
            }
        ]
        * 2,
        next_question="",
        **kw,
    )


def adapter(p):
    return SimpleNamespace(
        complete=AsyncMock(return_value=Result.ok(SimpleNamespace(content=json.dumps(p))))
    )


def test_evidence_and_required_decisions():
    messages = [{"role": "user", "kind": "text", "text": "Show tasks"}]
    assert asyncio.run(generate_preview(adapter(payload()), messages, "test")).decision == "preview"
    for change in (
        {"evidence": ["invented"]},
        {"decision": "ready", "required_decisions": ["public access?"]},
        {"decision": "ask", "next_question": ""},
    ):
        p = payload()
        p.update(change)
        with pytest.raises(ValueError):
            asyncio.run(generate_preview(adapter(p), messages, "test"))


def test_harness_correction_recovery_and_no_execution(tmp_path, monkeypatch):
    jobs = []

    def capture(self, sid, coro):
        jobs.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr(Harness, "_spawn", capture)
    h = Harness()
    s = h.create(
        {"goal": "Show tasks", "cwd": str(tmp_path), "preview_first": True, "backend": "litellm"}
    )
    assert jobs == ["_readiness_preview"]
    assert s["preview_first"] is True
    # Crash recovery preserves the user message and permits retry/correction.
    h = Harness()
    s = h.get(s["id"])
    assert s["status"] == "interrupted"
    h.send(s["id"], "No cards: plain text only")
    s = h.get(s["id"])
    assert s["messages"][-1]["text"] == "No cards: plain text only"
    for a in ("seed", "run", "suggest"):
        with pytest.raises(ValueError, match="permission"):
            h.action(s["id"], a, {})
    assert not h.get(s["id"]).get("seed_yaml")


def test_legacy_default_preserved(tmp_path, monkeypatch):
    jobs = []

    def capture(self, sid, coro):
        jobs.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr(Harness, "_spawn", capture)
    s = Harness().create({"goal": "Show tasks", "cwd": str(tmp_path), "preview_first": False})
    assert s["preview_first"] is False
    assert jobs == ["_interview_start"]


def test_preview_rejects_other_backends(tmp_path):
    with pytest.raises(ValueError, match="LiteLLM"):
        Harness().create(
            {
                "goal": "Show tasks",
                "cwd": str(tmp_path),
                "preview_first": True,
                "backend": "opencode",
            }
        )


def test_preview_adapter_forces_read_only(tmp_path, monkeypatch):
    captured = {}
    fake = adapter(payload())

    def factory(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr("ouroboros.providers.factory.create_llm_adapter", factory)
    monkeypatch.setattr(Harness, "_spawn", lambda _self, _sid, coro: coro.close())
    h = Harness()
    s = h.create(
        {
            "goal": "Show tasks",
            "cwd": str(tmp_path),
            "preview_first": True,
            "backend": "litellm",
            "model": "test",
        }
    )
    asyncio.run(h._readiness_preview(s["id"]))
    assert captured["permission_mode"] == "default"
    assert captured["strict_mcp_config"] is True
    assert captured["allowed_tools"] == []
    assert h.get(s["id"])["messages"][-1]["preview"]["decision"] == "preview"
    assert h.get(s["id"])["seed_ready"] is False


def test_old_codex_preview_cannot_resume_model(tmp_path, monkeypatch):
    monkeypatch.setattr(Harness, "_spawn", lambda _self, _sid, coro: coro.close())
    h = Harness()
    s = h.create(
        {"goal": "Show tasks", "cwd": str(tmp_path), "preview_first": True, "backend": "litellm"}
    )
    h._sessions[s["id"]]["backend"] = "codex"
    with pytest.raises(ValueError, match="LiteLLM"):
        asyncio.run(h._readiness_preview(s["id"]))


def ready_session(tmp_path, monkeypatch):
    from ouroboros.gui.readiness_preview import preview_digest

    monkeypatch.setattr(Harness, "_spawn", lambda _self, _sid, coro: coro.close())
    h = Harness()
    s = h.create({"goal": "Show tasks", "cwd": str(tmp_path), "execution_backend": "codex"})
    p = payload()
    p["decision"] = "ready"
    rev = preview_digest(s["id"], p, s["messages"])
    h._update(
        s["id"],
        lambda live: live.update(
            status="waiting_answer", current_preview=p, preview_revision=rev, seed_ready=True
        ),
    )
    return h, s["id"], rev, p


def test_reviewed_scope_seed_roundtrip_and_correction(tmp_path, monkeypatch):
    import yaml

    from ouroboros.core.seed import Seed

    h, sid, rev, p = ready_session(tmp_path, monkeypatch)
    for action in ("seed", "run"):
        with pytest.raises(ValueError):
            h.action(sid, action, {"revision": "old", "force": True})
    with pytest.raises(ValueError):
        h.action(sid, "run", {"revision": rev})
    created = h.action(sid, "seed", {"revision": rev})
    seed = Seed.from_dict(yaml.safe_load(created["seed_yaml"]))
    assert seed.goal == p["goal"]
    assert [c.description for c in seed.acceptance_criteria] == p["acceptance_criteria"]
    assert list(seed.constraints) == p["constraints"]
    assert list(seed.assumptions) == p["assumptions"]
    assert seed.metadata.ambiguity_score is None
    assert seed.metadata.generation_mode == "reviewed_console_preview"
    assert not created.get("execution_id")
    assert created["status"] == "seed_ready"
    restored = Harness().get(sid)
    assert restored["approved_revision"] == rev
    assert restored["seed_yaml"] == created["seed_yaml"]
    h.send(sid, "Only show completed tasks")
    corrected = h.get(sid)
    assert not corrected.get("seed_yaml")
    assert not corrected.get("approved_revision")
    assert not corrected.get("preview_revision")
    # Old Seed remains visibly archived in messages but cannot be executed.
    assert any(m["kind"] == "seed" for m in corrected["messages"])
    with pytest.raises(ValueError):
        h.action(sid, "run", {"revision": rev})


def test_run_is_separate_and_uses_execution_backend(tmp_path, monkeypatch):
    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    h.action(sid, "seed", {"revision": rev})
    assert h._handlers_for(h.get(sid)).backend == "codex"
    jobs = []

    def capture(_self, _sid, coro):
        jobs.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr(Harness, "_spawn", capture)
    monkeypatch.setattr("ouroboros.gui.harness._workspace_problem", lambda _cwd: None)
    h.action(sid, "run", {"revision": rev})
    assert jobs == ["_start_run"]
    with pytest.raises(ValueError):
        h.action(sid, "run", {"revision": rev})
    with pytest.raises(ValueError):
        h.send(sid, "Change while running")


def test_tampered_scope_or_seed_and_cross_session_cannot_run(tmp_path, monkeypatch):
    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    h.action(sid, "seed", {"revision": rev})
    h._sessions[sid]["seed_yaml"] += "\n# edited\n"
    with pytest.raises(ValueError):
        h.action(sid, "run", {"revision": rev})
    h._sessions[sid]["current_preview"]["goal"] = "different scope"
    with pytest.raises(ValueError):
        h.action(sid, "seed", {"revision": rev})
    other = h.create({"goal": "Show tasks", "cwd": str(tmp_path)})
    with pytest.raises(ValueError):
        h.action(other["id"], "seed", {"revision": rev})


def test_model_preview_cannot_force_seed_before_ready(tmp_path, monkeypatch):
    from ouroboros.gui.readiness_preview import preview_digest

    h, sid, _, p = ready_session(tmp_path, monkeypatch)
    p.update(decision="preview", required_decisions=["Public access policy?"])
    rev = preview_digest(sid, p, h.get(sid)["messages"])
    h._update(sid, lambda live: live.update(current_preview=p, preview_revision=rev))
    with pytest.raises(ValueError, match="required decisions"):
        h.action(sid, "seed", {"revision": rev, "force": True})


def test_one_concrete_scene_is_enough_for_a_small_task():
    p = payload()
    p.update(decision="ready", scenes=p["scenes"][:1])
    messages = [{"role": "user", "kind": "text", "text": "Show tasks"}]
    assert asyncio.run(generate_preview(adapter(p), messages, "test")).decision == "ready"
    p["scenes"] = []
    with pytest.raises(ValueError, match="concrete scene"):
        asyncio.run(generate_preview(adapter(p), messages, "test"))


def test_preview_uses_execute_stage_default(tmp_path, monkeypatch):
    monkeypatch.setattr(Harness, "_spawn", lambda _self, _sid, coro: coro.close())
    monkeypatch.setattr(
        "ouroboros.gui.settings.SettingsModel.effective_stage_backend", lambda _self, _stage: "codex"
    )
    s = Harness().create({"goal": "Show tasks", "cwd": str(tmp_path)})
    assert s["execution_backend"] == "codex"


@pytest.mark.parametrize(
    "status,terminal,expected_job",
    [
        ("interrupted", None, "to_thread"),
        ("interrupted", {"status": "completed"}, "to_thread"),
        ("failed", None, "to_thread"),
        ("failed", {"status": "failed"}, "_start_run"),
    ],
)
def test_existing_execution_reconnect_or_confirmed_retry(
    tmp_path, monkeypatch, status, terminal, expected_job
):
    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    h.action(sid, "seed", {"revision": rev})
    h._update(sid, lambda s: s.update(status=status, execution_id="exec_old", run_job_id="job_old"))
    monkeypatch.setattr("ouroboros.gui.harness._job_terminal", lambda *_args: terminal)
    monkeypatch.setattr("ouroboros.gui.harness._workspace_problem", lambda _cwd: None)
    jobs = []

    def capture(_self, _sid, coro):
        jobs.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr(Harness, "_spawn", capture)
    h.action(sid, "run", {"revision": rev})
    assert jobs == [expected_job]
    s = h.get(sid)
    assert s.get("run_attempt", 0) == (1 if expected_job == "_start_run" else 0)
    assert s.get("execution_id") == (None if expected_job == "_start_run" else "exec_old")


def test_unknown_live_execution_blocks_scope_change(tmp_path, monkeypatch):
    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    h.action(sid, "seed", {"revision": rev})
    h._update(
        sid, lambda s: s.update(status="interrupted", execution_id="exec_old", run_job_id="job_old")
    )
    monkeypatch.setattr("ouroboros.gui.harness._job_terminal", lambda *_args: None)
    with pytest.raises(ValueError, match="existing execution"):
        h.send(sid, "Change task")
    assert h.get(sid)["approved_revision"] == rev


def test_unknown_acceptance_is_persisted_and_blocks_duplicate_and_correction(tmp_path, monkeypatch):
    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    h.action(sid, "seed", {"revision": rev})

    async def lost_receipt(seed, **kw):
        assert Harness().get(sid)["run_start_pending"] is True
        raise RuntimeError("lost receipt after dispatch")

    monkeypatch.setattr(
        h, "_handlers_for", lambda _s: SimpleNamespace(run_starter=lambda _cwd: lost_receipt)
    )
    with pytest.raises(RuntimeError, match="lost receipt"):
        asyncio.run(h._start_run(sid))
    restored = Harness()
    assert restored.get(sid)["run_start_pending"] is True
    with pytest.raises(ValueError, match="uncertain"):
        restored.action(sid, "run", {"revision": rev})
    with pytest.raises(ValueError, match="uncertain"):
        restored.send(sid, "new scope")


@pytest.mark.parametrize("terminal", ["cancelled", "interrupted"])
def test_job_terminal_without_execution_terminal_stops_following(tmp_path, monkeypatch, terminal):
    h, sid, _, _ = ready_session(tmp_path, monkeypatch)
    h._update(
        sid, lambda s: s.update(status="running", execution_id="exec_test", run_job_id="job_test")
    )
    monkeypatch.setattr(
        "ouroboros.dashboard_web.reader.EventTail",
        lambda *_args: SimpleNamespace(fetch_new=lambda: []),
    )
    monkeypatch.setattr(
        "ouroboros.gui.harness._job_terminal",
        lambda *_args: {"status": terminal, "message": terminal},
    )
    monkeypatch.setattr("ouroboros.gui.harness._run_result", lambda *_args: None)
    h._follow_run(sid, "exec_test", "job_test")
    assert h.get(sid)["status"] == "failed"
    assert h.get(sid)["messages"][-1]["text"] == terminal
