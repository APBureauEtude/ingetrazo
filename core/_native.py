# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""The experimental Rust engine (``rust/ingetrazo_core``, built with maturin).

``native`` is the compiled module when the engine is on and loads, else
``None``. It is OFF unless Preferences ▸ General ▸ «Rust engine
(experimental)» turns it on (read once, so it applies at the next start);
``INGETRAZO_RUST=1`` / ``=0`` overrides the setting, for tests and benches.
Every caller keeps its Python code and uses it whenever ``native`` is
``None``: the kernels make things faster, never different.

``native`` is resolved on first use, not at import: the setting lives in
QSettings, which needs the application's name set first."""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

#: The General setting that turns the engine on ("1") or off ("0").
SETTING = "rust_engine"

_UNSET = object()
_module = _UNSET          # the compiled module, None, or not looked at yet


def available():
    """The compiled module if this build has it and it loads, else None —
    whatever the setting says (Preferences shows «not available»)."""
    global _module
    if _module is _UNSET:
        try:
            import ingetrazo_core as mod
        except Exception as exc:  # noqa: BLE001 — a missing module is the norm
            mod = None
            if not isinstance(exc, ImportError):
                log.warning("Rust engine failed to load, using Python: %s",
                            exc)
        _module = mod
    return _module


def wanted() -> bool:
    """Whether the engine is asked for: the environment first, then the
    saved preference (off by default)."""
    env = os.environ.get("INGETRAZO_RUST")
    if env is not None:
        return env != "0"
    try:
        from core import general_settings
        return str(general_settings.value(SETTING, "0")) == "1"
    except Exception:  # noqa: BLE001 — no Qt settings yet: stay on Python
        return False


def __getattr__(name):
    if name == "native":
        mod = available() if wanted() else None
        globals()["native"] = mod       # fixed for the whole session
        return mod
    raise AttributeError(name)


def engine() -> str:
    """«Rust» or «Python», for About and the logs."""
    import core._native as me
    return "Rust" if me.native is not None else "Python"
