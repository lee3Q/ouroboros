import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ouroboros.core.types import Result
from ouroboros.gui.harness import Harness, Refusal
from ouroboros.gui.readiness_preview import generate_preview


@pytest.fixture(autouse=True)
def isolated_preview_runtime(monkeypatch):
    """Never depend on installed CLIs or start a real model/background job."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Readiness tests must not launch subprocesses or real models")

    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("ouroboros.providers.factory.create_llm_adapter", forbidden)
    monkeypatch.setattr(
        "ouroboros.backends.model_catalog.detect_backend_cli", lambda _backend: "/mock/agent"
    )
    monkeypatch.setattr(
        "ouroboros.gui.settings.SettingsModel.effective_stage_backend",
        lambda _self, _stage: "codex",
    )
    monkeypatch.setattr(Harness, "_spawn", lambda _self, _sid, coro: coro.close())


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


@pytest.mark.parametrize("backend", [None, "litellm", "codex", "opencode"])
def test_preview_default_preserves_explicit_native_backend(tmp_path, monkeypatch, backend):
    jobs = []

    def capture(_self, _sid, coro):
        jobs.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr(Harness, "_spawn", capture)
    request = {"goal": "Show tasks", "cwd": str(tmp_path)}
    if backend is not None:
        request["backend"] = backend
    s = Harness().create(request)
    preview = backend in (None, "litellm")
    assert s["preview_first"] is preview
    assert s["backend"] == ("litellm" if preview else backend)
    assert jobs == ["_readiness_preview" if preview else "_interview_start"]
    assert not s.get("seed_yaml")
    assert not s.get("execution_id")


@pytest.mark.parametrize(
    "backend,code", [("litellm", "backend_wrong_mode"), ("unknown-runtime", "backend_unknown")]
)
def test_preview_rejects_invalid_execution_backend_before_saving(tmp_path, backend, code):
    h = Harness()
    with pytest.raises(Refusal) as refused:
        h.create({"goal": "Show tasks", "cwd": str(tmp_path), "execution_backend": backend})
    assert refused.value.code == code
    assert h.list_sessions() == []
    assert Harness().list_sessions() == []


def test_preview_rejects_missing_execution_cli_before_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ouroboros.backends.model_catalog.detect_backend_cli", lambda _backend: None
    )
    h = Harness()
    with pytest.raises(Refusal) as refused:
        h.create({"goal": "Show tasks", "cwd": str(tmp_path), "execution_backend": "codex"})
    assert refused.value.code == "backend_not_installed"
    assert h.list_sessions() == []
    assert Harness().list_sessions() == []


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
    assert not corrected.get("approved_seed_digest")
    assert not corrected.get("preview_revision")
    assert not corrected.get("current_preview")
    assert corrected["seed_ready"] is False
    assert corrected["messages"][-1]["text"] == "Only show completed tasks"
    # Old Seed remains visibly archived in messages but cannot be executed.
    archived = [m for m in corrected["messages"] if m["kind"] == "seed"]
    assert len(archived) == 1
    assert archived[0]["seed_yaml"] == created["seed_yaml"]
    reloaded = Harness().get(sid)
    assert reloaded["messages"] == corrected["messages"]
    assert not reloaded.get("seed_yaml")
    assert not reloaded.get("current_preview")
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
    monkeypatch.setattr(Harness, "_ready_folder", lambda _self, _session, **_kwargs: None)
    h.action(sid, "run", {"revision": rev})
    assert jobs == ["_start_run"]
    with pytest.raises(ValueError):
        h.action(sid, "run", {"revision": rev})
    with pytest.raises(ValueError):
        h.send(sid, "Change while running")


@pytest.mark.parametrize("kind,result", [("not_repo", "initialized"), ("no_commits", "committed")])
def test_preview_run_keeps_explicit_git_preparation(tmp_path, monkeypatch, kind, result):
    from ouroboros.gui import workspace

    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    approved = h.action(sid, "seed", {"revision": rev})
    monkeypatch.setattr(
        "ouroboros.gui.harness.workspace.git_state", lambda _cwd: workspace.GitState(kind)
    )
    prepare_git = Mock(return_value=result)
    monkeypatch.setattr("ouroboros.gui.harness.workspace.prepare_git", prepare_git)
    jobs = []

    def capture(_self, _sid, coro):
        jobs.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr(Harness, "_spawn", capture)
    with pytest.raises(Refusal) as refused:
        h.action(sid, "run", {"revision": rev})
    assert refused.value.code == "needs_git"
    prepare_git.assert_not_called()
    assert jobs == []
    assert h.get(sid)["status"] == "seed_ready"
    assert h.get(sid)["seed_yaml"] == approved["seed_yaml"]
    assert h.get(sid)["approved_revision"] == rev

    started = h.action(sid, "run", {"revision": rev, "prepare_git": True})
    prepare_git.assert_called_once_with(str(tmp_path))
    assert jobs == ["_start_run"]
    assert started["status"] == "running"
    assert started["seed_yaml"] == approved["seed_yaml"]
    assert any(m.get("key") == f"git_{result}" for m in started["messages"])
    with pytest.raises(ValueError):
        h.action(sid, "run", {"revision": rev, "prepare_git": True})
    prepare_git.assert_called_once()
    assert jobs == ["_start_run"]


@pytest.mark.parametrize("prepare", ["true", 1, None])
def test_preview_rejects_non_boolean_git_permission(tmp_path, monkeypatch, prepare):
    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    approved = h.action(sid, "seed", {"revision": rev})
    ready_folder = Mock()
    monkeypatch.setattr(Harness, "_ready_folder", ready_folder)
    with pytest.raises(Refusal) as refused:
        h.action(sid, "run", {"revision": rev, "prepare_git": prepare})
    assert refused.value.code == "bad_prepare_git"
    ready_folder.assert_not_called()
    assert h.get(sid)["status"] == "seed_ready"
    assert h.get(sid)["seed_yaml"] == approved["seed_yaml"]


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
        "ouroboros.gui.settings.SettingsModel.effective_stage_backend",
        lambda _self, _stage: "opencode",
    )
    s = Harness().create({"goal": "Show tasks", "cwd": str(tmp_path)})
    assert s["execution_backend"] == "opencode"


@pytest.mark.parametrize(
    "status,terminal,expected_job",
    [
        ("interrupted", None, "to_thread"),
        ("interrupted", {"status": "completed"}, "to_thread"),
        ("failed", None, "to_thread"),
        ("failed", {"status": "completed"}, "to_thread"),
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
    monkeypatch.setattr(Harness, "_ready_folder", lambda _self, _session, **_kwargs: None)
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


@pytest.mark.parametrize("receipt", [{}, {"execution_id": "exec_test"}, {"job_id": "job_test"}])
def test_incomplete_dispatch_receipt_blocks_retry_after_reload(tmp_path, monkeypatch, receipt):
    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    approved = h.action(sid, "seed", {"revision": rev})
    starter = AsyncMock(return_value=receipt)
    monkeypatch.setattr(
        h, "_handlers_for", lambda _s: SimpleNamespace(run_starter=lambda _cwd: starter)
    )
    with pytest.raises(ValueError, match="receipt is incomplete"):
        asyncio.run(h._start_run(sid))
    starter.assert_awaited_once()
    restored = Harness()
    assert restored.get(sid)["run_start_pending"] is True
    assert restored.get(sid)["seed_yaml"] == approved["seed_yaml"]
    with pytest.raises(ValueError, match="uncertain"):
        restored.action(sid, "run", {"revision": rev})
    with pytest.raises(ValueError, match="uncertain"):
        restored.send(sid, "Change the scope")
    starter.assert_awaited_once()


def test_confirmed_dispatch_uses_approved_seed_and_reconnects_without_resubmission(
    tmp_path, monkeypatch
):
    import yaml

    h, sid, rev, _ = ready_session(tmp_path, monkeypatch)
    approved = h.action(sid, "seed", {"revision": rev})
    starter = AsyncMock(
        return_value={"execution_id": "exec_test", "job_id": "job_test", "session_id": "orch_test"}
    )
    monkeypatch.setattr(
        h, "_handlers_for", lambda _s: SimpleNamespace(run_starter=lambda _cwd: starter)
    )
    follow = Mock()
    monkeypatch.setattr(Harness, "_follow_run", follow)
    monkeypatch.setattr(Harness, "_ready_folder", lambda _self, _session, **_kwargs: None)
    h.action(sid, "run", {"revision": rev})
    asyncio.run(h._start_run(sid))
    starter.assert_awaited_once()
    seed = starter.await_args.args[0]
    assert seed.to_dict() == yaml.safe_load(approved["seed_yaml"])
    assert starter.await_args.kwargs["idempotency_key"] == f"gui-{sid}-{seed.metadata.seed_id}-0"
    follow.assert_called_once_with(sid, "exec_test", "job_test")

    restored = Harness()
    assert restored.get(sid)["status"] == "interrupted"
    assert restored.get(sid)["run_start_pending"] is False
    assert restored.get(sid)["run_job_id"] == "job_test"
    monkeypatch.setattr("ouroboros.gui.harness._job_terminal", lambda *_args: None)
    redispatch = AsyncMock(side_effect=AssertionError("Known receipt must only reconnect"))
    monkeypatch.setattr(Harness, "_start_run", redispatch)
    jobs = []

    def capture(_self, _sid, coro):
        jobs.append(coro.cr_code.co_name)
        asyncio.run(coro)

    monkeypatch.setattr(Harness, "_spawn", capture)
    restored.action(sid, "run", {"revision": rev})
    assert jobs == ["to_thread"]
    assert restored.get(sid)["execution_id"] == "exec_test"
    assert restored.get(sid).get("run_attempt", 0) == 0
    follow.assert_called_with(sid, "exec_test", "job_test")
    assert follow.call_count == 2
    redispatch.assert_not_called()
    starter.assert_awaited_once()


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
