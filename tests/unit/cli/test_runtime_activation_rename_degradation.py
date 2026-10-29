"""#2294 finding 5: runtime activation no-replace rename degrades like Codex."""

from __future__ import annotations

import ctypes
import errno
from pathlib import Path

import pytest

from ouroboros.cli import runtime_activation


def _fake_libc(error_number: int | None) -> object:
    class _FakeRenameat2:
        argtypes = None
        restype = None

        def __call__(self, *args: object) -> int:
            if error_number is not None:
                ctypes.set_errno(error_number)
                return 1
            return 0

    class _FakeLibc:
        renameat2 = _FakeRenameat2()

    return _FakeLibc()


def test_degrades_to_link_fallback_on_unsupported_flag(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "claim"
    source.write_text("fresh\n", encoding="utf-8")
    destination = tmp_path / "target"
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: _fake_libc(errno.EINVAL))
    monkeypatch.setattr(runtime_activation.sys, "platform", "linux")
    runtime_activation._rename_if_absent(source, destination)
    assert destination.read_text(encoding="utf-8") == "fresh\n"
    assert not source.exists()


def test_degrades_to_fallback_when_primitive_missing(tmp_path: Path, monkeypatch) -> None:
    class _NoPrimitive:
        pass

    source = tmp_path / "claim"
    source.write_text("fresh\n", encoding="utf-8")
    destination = tmp_path / "target"
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: _NoPrimitive())
    monkeypatch.setattr(runtime_activation.sys, "platform", "linux")
    runtime_activation._rename_if_absent(source, destination)
    assert destination.read_text(encoding="utf-8") == "fresh\n"
    assert not source.exists()


def test_degradation_refuses_occupied_destination(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "claim"
    source.write_text("fresh\n", encoding="utf-8")
    destination = tmp_path / "target"
    destination.write_text("mine\n", encoding="utf-8")
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: _fake_libc(errno.EINVAL))
    monkeypatch.setattr(runtime_activation.sys, "platform", "linux")
    with pytest.raises(FileExistsError):
        runtime_activation._rename_if_absent(source, destination)
    assert destination.read_text(encoding="utf-8") == "mine\n"


def test_unrelated_primitive_error_still_raises(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "claim"
    source.write_text("fresh\n", encoding="utf-8")
    destination = tmp_path / "target"
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: _fake_libc(errno.EPERM))
    monkeypatch.setattr(runtime_activation.sys, "platform", "linux")
    with pytest.raises(OSError):
        runtime_activation._rename_if_absent(source, destination)


def _fake_darwin_libc(error_number: int | None, calls: list | None = None) -> object:
    class _FakeRenameatxNp:
        argtypes = None
        restype = None

        def __call__(self, *args: object) -> int:
            if calls is not None:
                calls.append(args)
            if error_number is not None:
                ctypes.set_errno(error_number)
                return 1
            return 0

    class _FakeLibc:
        renameatx_np = _FakeRenameatxNp()

    return _FakeLibc()


def test_darwin_missing_renameatx_np_degrades(tmp_path: Path, monkeypatch) -> None:
    # Negative case: only the wrong-named symbol exists; the checked callable
    # must be the same one that is called.
    class _WrongSymbolOnly:
        renamex_np = object()

    source = tmp_path / "claim"
    source.write_text("fresh\n", encoding="utf-8")
    destination = tmp_path / "target"
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: _WrongSymbolOnly())
    monkeypatch.setattr(runtime_activation.sys, "platform", "darwin")
    runtime_activation._rename_if_absent(source, destination)
    assert destination.read_text(encoding="utf-8") == "fresh\n"
    assert not source.exists()


def test_darwin_present_uses_renameatx_np_with_exclusive_flag(tmp_path: Path, monkeypatch) -> None:
    calls: list = []
    source = tmp_path / "claim"
    destination = tmp_path / "target"
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: _fake_darwin_libc(None, calls))
    monkeypatch.setattr(runtime_activation.sys, "platform", "darwin")
    monkeypatch.setattr(runtime_activation.os, "rename", lambda *_a, **_k: None)
    runtime_activation._rename_if_absent(source, destination)
    assert len(calls) == 1
    assert calls[0][-1] == 0x00000004  # RENAME_EXCL passed to renameatx_np


def test_darwin_unsupported_flag_degrades(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "claim"
    source.write_text("fresh\n", encoding="utf-8")
    destination = tmp_path / "target"
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: _fake_darwin_libc(errno.EINVAL))
    monkeypatch.setattr(runtime_activation.sys, "platform", "darwin")
    runtime_activation._rename_if_absent(source, destination)
    assert destination.read_text(encoding="utf-8") == "fresh\n"
    assert not source.exists()
