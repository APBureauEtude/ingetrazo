# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Ambient occlusion of the 3D view (#954): off, the picture is the one it
always was; on, the foot of a box on a floor darkens and the open floor
does not; the foliage mark rides the recorded instanced passes (the native
replay gained glStencilFunc for it, in the same order on both sides).

The rendering cases need a GL context; skipped where there is none."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtGui import QImage, QVector3D
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from views import ambient_occlusion as ao  # noqa: E402
import views.viewport as viewport  # noqa: E402


def test_it_is_off_unless_asked(monkeypatch):
    monkeypatch.delenv("INGETRAZO_AO", raising=False)
    assert ao.settings_from_env() is None
    monkeypatch.setenv("INGETRAZO_AO", "0")
    assert ao.settings_from_env() is None


def test_the_settings_are_kept_in_range(monkeypatch):
    monkeypatch.setenv("INGETRAZO_AO", "1")
    monkeypatch.setenv("INGETRAZO_AO_RADIUS", "-3")
    monkeypatch.setenv("INGETRAZO_AO_SAMPLES", "500")
    monkeypatch.setenv("INGETRAZO_AO_INTENSITY", "nada")
    s = ao.settings_from_env()
    assert s["radius"] > 0 and s["samples"] == 64 and s["intensity"] == 1.0


def test_the_tape_records_the_foliage_mark_for_the_native_replay():
    calls = []
    tape = viewport._GlTape()
    tape.stencil_func(lambda *a: calls.append(a), viewport.GL_ALWAYS,
                      viewport.AO_FOLIAGE_BIT, 0xFF)
    assert calls == [(viewport.GL_ALWAYS, viewport.AO_FOLIAGE_BIT, 0xFF)]
    assert tape.ops[-1][:4] == (tape.STENCIL, viewport.GL_ALWAYS,
                                viewport.AO_FOLIAGE_BIT, 0xFF)
    # GlReplay takes the entry points in opcode order.
    assert viewport._TAPE_FUNCS[tape.STENCIL] == b"glStencilFunc"
    assert len(viewport._TAPE_FUNCS) == tape.STENCIL + 1


def _lum(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format_RGBA8888)
    buf = np.frombuffer(img.constBits(), np.uint8)
    px = buf.reshape(img.height(), img.bytesPerLine())[:, :img.width() * 4]
    return px.reshape(img.height(), img.width(), 4)[..., :3].astype(
        np.float32).mean(axis=2)


@pytest.fixture
def box_on_floor():
    from views.main_window import MainWindow
    win = MainWindow()
    try:
        win.show()
        _app.processEvents()
        vp = win.viewport
        if getattr(vp, "_gl", None) is None or not vp.isValid():
            pytest.skip("no OpenGL context on this platform")
        V = QVector3D
        scene = vp.scene
        scene.mesh.add_face([V(-10, -10, 0), V(10, -10, 0), V(10, 10, 0),
                             V(-10, 10, 0)])
        p = [V(-1, -1, 0), V(1, -1, 0), V(1, 1, 0), V(-1, 1, 0),
             V(-1, -1, 2), V(1, -1, 2), V(1, 1, 2), V(-1, 1, 2)]
        for idx in ((4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
                    (2, 3, 7, 6), (3, 0, 4, 7)):
            scene.mesh.add_face([p[i] for i in idx])
        scene.version += 1
        vp.camera.set_view("iso")
        vp.camera.fit_to(V(-4, -4, 0), V(4, 4, 2))
        for _ in range(5):
            _app.processEvents()
        yield vp
    finally:
        win._saved_version = win.viewport.scene.version
        win.close()


def _render(vp, monkeypatch, on: str) -> np.ndarray:
    monkeypatch.setenv("INGETRAZO_AO", on)
    monkeypatch.setenv("INGETRAZO_AO_RADIUS", "0.5")
    return _lum(vp.render_image(400, 300, overlays=False))


def test_the_foot_of_a_box_darkens_and_the_open_floor_does_not(
        box_on_floor, monkeypatch):
    vp = box_on_floor
    off = _render(vp, monkeypatch, "0")
    on = _render(vp, monkeypatch, "1")
    if getattr(vp, "_ao", None) is not None and vp._ao.broken:
        pytest.skip(f"this driver refuses the pass: {vp._ao.broken}")
    darker = off - on
    assert (darker > 8).mean() > 0.002          # the corner band shows
    assert (on > off + 1).mean() < 0.001        # it never lightens
    assert (np.abs(darker) < 1).mean() > 0.6    # most of the picture is as it was
    # Off again: the very same picture as before it was ever on.
    assert np.array_equal(_render(vp, monkeypatch, "0"), off)


def test_wireframe_has_none(box_on_floor, monkeypatch):
    vp = box_on_floor
    vp.plano_style = "lineas"                   # the wireframe face mode
    assert np.array_equal(_render(vp, monkeypatch, "0"),
                          _render(vp, monkeypatch, "1"))
