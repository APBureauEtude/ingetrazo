# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""With the experimental engine, the corner a drawing tool acquires and
whether a point is hidden are answered for the lazy placements without
baking them (#158) — and they are the answers of the pick index that holds
every placement baked: the same corner, bit for bit, at every pixel of a
few views over turned, scaled and mirrored copies that hide one another.
Skipped without the engine."""
from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtGui import QMatrix4x4, QVector3D as V  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import core._native as _native  # noqa: E402

_app = QApplication.instance() or QApplication([])
mod = _native.native            # the engine on (INGETRAZO_RUST), not only built
pytestmark = pytest.mark.skipif(
    mod is None or not hasattr(mod, "InstanceSet")
    or not hasattr(mod.InstanceSet, "corners_near"),
    reason="native module not built")


def _cube(sx=1.0, sy=1.0, sz=1.0, at=(0.0, 0.0, 0.0)):
    from core.mesh import Mesh
    m = Mesh()
    o = V(*at)
    p = [o + V(0, 0, 0), o + V(sx, 0, 0), o + V(sx, sy, 0), o + V(0, sy, 0),
         o + V(0, 0, sz), o + V(sx, 0, sz), o + V(sx, sy, sz),
         o + V(0, sy, sz)]
    for idx in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
                (2, 3, 7, 6), (3, 0, 4, 7)):
        m.add_face([p[i] for i in idx])
    return m


def _window(lazy):
    from core.group import Group
    from views.main_window import MainWindow
    win = MainWindow()
    vp = win.viewport
    vp.resize(900, 640)
    vp.scene.guides.clear()
    rng = np.random.default_rng(7)
    protos = [_cube(), _cube(2.0, 0.5, 1.5), _cube(0.3, 0.3, 3.0)]
    for i in range(8):
        for j in range(6):
            g = Group(protos[(i + j) % 3], name=f"C{i}{j}")
            m = QMatrix4x4()
            m.translate(2.2 * i + 0.13 * j, 2.4 * j - 0.07 * i,
                        float(rng.uniform(0, 1.5)))
            m.rotate(float(rng.uniform(0, 360)), *rng.uniform(-1, 1, 3))
            s = rng.uniform(0.5, 1.4, 3)
            if (i * 6 + j) % 7 == 3:
                s[1] = -s[1]                         # mirrored
            m.scale(*s)
            g.xform = m
            vp.scene.groups.append(g)
    by = {g.name: g for g in vp.scene.groups}
    by["C23"].hidden = True             # neither hides nor snaps
    by["C51"].locked = True             # hides, but does not snap
    for k, (x, y) in enumerate(((5.1, 3.3), (11.7, 8.2), (1.4, 12.6))):
        m = _cube(1.0 + 0.4 * k, 0.8, 2.0 - 0.3 * k, (x, y, 0.4 * k))
        vp.scene.groups.append(Group(m, name=f"G{k}"))   # fixed: no matrix
    vp.scene.groups[-1].hidden = True   # a fixed one that hides nothing
    loose = _cube(3.0, 0.2, 2.5, (7.3, 6.1, 0.0))        # the loose part
    for f in loose.faces:
        vp.scene.mesh.add_face(list(f.vertices))
    # A wall of hidden loose faces: in the index, hiding nothing.
    wall = _cube(0.1, 9.0, 4.0, (9.9, 1.0, -0.5))
    for f in wall.faces:
        g = vp.scene.mesh.add_face(list(f.vertices))
        g.attrs["hidden"] = True
    vp.scene.version += 1
    vp._PICK_LAZY_MIN_FACES = 1 if lazy else 10 ** 9
    return win, vp


def _close(win):
    win._saved_version = win.viewport.scene.version
    win.close()


VIEWS = ((30.0, 35.0, True), (200.0, 20.0, True), (115.0, 60.0, False),
         (300.0, 10.0, True))


def _set_view(vp, view):
    yaw, pitch, persp = view
    cam = vp.camera
    cam.perspective = persp
    cam.fit_to(V(-1, -1, -1), V(18, 14, 4))
    cam.yaw, cam.pitch = math.radians(yaw), math.radians(pitch)
    vp._tick = getattr(vp, "_tick", 0) + 1


def _key(p):
    return None if p is None else (p.x(), p.y(), p.z())


@pytest.fixture
def pair():
    a, va = _window(lazy=True)
    b, vb = _window(lazy=False)
    try:
        yield va, vb
    finally:
        _close(a)
        _close(b)


def test_the_unbaked_corner_is_the_baked_one_everywhere(pair):
    va, vb = pair
    assert va._pick_lazy_table() is not None
    assert vb._pick_lazy_table() is None
    seen = 0
    for view in VIEWS:
        _set_view(va, view)
        _set_view(vb, view)
        assert va._lazy_native() is not None
        for x in np.arange(13.37, 900, 17.0):
            for y in np.arange(9.71, 640, 19.0):
                va._input_serial = vb._input_serial = (x, y)
                got = va.pick_vertex(float(x), float(y))
                want = vb.pick_vertex(float(x), float(y))
                assert _key(got) == _key(want), (view, x, y)
                seen += got is not None
    # Nothing was baked to answer.
    assert not getattr(va, "_pick_live", None)
    assert seen > 100


def test_a_point_is_hidden_unbaked_as_it_is_baked(pair):
    va, vb = pair
    rng = np.random.default_rng(3)
    hidden = 0
    for view in VIEWS:
        _set_view(va, view)
        _set_view(vb, view)
        pts = [V(*rng.uniform((-1, -1, -1), (18, 14, 4)))
               for _ in range(300)]
        # Corners of the copies too: on their own faces, never behind them.
        for g in va.scene.groups[::5]:
            if getattr(g, "xform", None) is not None:
                pts.append(g.xform.map(V(0, 0, 0)))
        got = va._occluded_many(pts)
        want = vb._occluded_many(pts)
        assert got == want, view
        assert [va._is_occluded(p) for p in pts[:40]] == want[:40]
        hidden += sum(want)
    assert 0 < hidden < 4 * 300
    assert not getattr(va, "_pick_live", None)
