# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""The experimental Rust engine is OFF unless Preferences turns it on, and
INGETRAZO_RUST overrides the preference either way (tests, benches)."""
from __future__ import annotations

import importlib

import pytest

import core._native as _native
from core import general_settings


@pytest.fixture
def fresh(monkeypatch):
    """A newly imported core._native (``native`` is fixed per session)."""
    def make():
        _native.__dict__.pop("native", None)
        return importlib.reload(_native)
    saved = _native.__dict__.get("native", _native)
    yield make
    general_settings.set_value(_native.SETTING, "0")
    make()
    if saved is not _native:
        _native.native = saved      # what the rest of the session saw


def test_off_by_default(fresh, monkeypatch):
    monkeypatch.delenv("INGETRAZO_RUST", raising=False)
    general_settings.set_value(_native.SETTING, "0")
    mod = fresh()
    assert mod.native is None
    assert mod.engine() == "Python"


def test_preference_turns_it_on(fresh, monkeypatch):
    if _native.available() is None:
        pytest.skip("native module not built")
    monkeypatch.delenv("INGETRAZO_RUST", raising=False)
    general_settings.set_value(_native.SETTING, "1")
    mod = fresh()
    assert mod.native is not None
    assert mod.engine() == "Rust"


@pytest.mark.parametrize("env,pref,on", [("0", "1", False), ("1", "0", True)])
def test_environment_overrides_preference(fresh, monkeypatch, env, pref, on):
    if on and _native.available() is None:
        pytest.skip("native module not built")
    monkeypatch.setenv("INGETRAZO_RUST", env)
    general_settings.set_value(_native.SETTING, pref)
    mod = fresh()
    assert (mod.native is not None) is on
