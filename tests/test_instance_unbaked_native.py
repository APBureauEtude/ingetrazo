# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""What the native InstanceSet answers for placements it does not bake is
what the pick index finds in their bakes (#158): for random prototypes
under random placement matrices (mirrors, scales, rotations), the hard-edge
ends near a pixel are the baked ends, bit for bit, at the very pixels
``Viewport._project_px`` gives them; and a point is hidden exactly when the
occlusion block over the baked triangles says so — but for the rays it
marks as too close to call, which the triangles ``ray_tris`` gives settle
as that block does. Skipped without the module."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtGui import QMatrix4x4, QVector3D  # noqa: E402

import core._native as _native  # noqa: E402

mod = _native.available()
pytestmark = pytest.mark.skipif(
    mod is None or not hasattr(mod, "InstanceSet")
    or not hasattr(mod.InstanceSet, "corners_near"),
    reason="native module not built")

W, H = 1200, 800


def _proto(rng, big=False):
    # Big ones (hundreds to thousands of edges) go through the edge BVH.
    n = int(rng.integers(300, 3000)) if big else int(rng.integers(1, 60))
    c = rng.uniform(-2, 2, size=(n, 1, 3))
    tri = c + rng.normal(scale=rng.choice([0.05, 0.5, 2.0]), size=(n, 3, 3))
    v0 = tri[:, 0]
    e1 = tri[:, 1] - v0
    e2 = tri[:, 2] - v0
    # Hard edges are kept as float32, as the bake keeps them.
    edges = (tri[:, :2].reshape(-1, 6)[: int(rng.integers(0, n + 1))]
             .astype(np.float32).astype(np.float64))
    return v0, e1, e2, edges


def _matrix(rng):
    m = QMatrix4x4()
    m.translate(*rng.uniform(-30, 30, 3))
    m.rotate(float(rng.uniform(0, 360)), *rng.uniform(-1, 1, 3))
    s = rng.uniform(0.2, 3, 3)
    if rng.random() < 0.3:
        s[0] = -s[0]                                  # mirrored
    m.scale(*s)
    return m


def _bake(proto, xf):
    """The placement as ``Viewport._instance_chunk`` bakes it."""
    from views.viewport import _placed_maps
    v0, e1, e2, edges = proto
    _L, tv, tp = _placed_maps(xf)
    ends = tp(edges.reshape(-1, 3)).astype(np.float32).astype(np.float64)
    return tp(v0), tv(e1), tv(e2), ends.reshape(-1, 2, 3)


class _Eye:
    """What Viewport._project_px reads of a viewport."""

    def __init__(self, mvp):
        self._m = np.array(mvp.data(), dtype=np.float64).reshape(4, 4,
                                                                 order="F")

    def _np_mvp(self):
        return self._m

    def width(self):
        return W

    def height(self):
        return H


def _camera(rng):
    proj = QMatrix4x4()
    if rng.random() < 0.5:
        proj.perspective(50.0, W / H, 0.5, 500.0)
    else:
        proj.ortho(-60, 60, -40, 40, -500, 500)
    view = QMatrix4x4()
    eye = rng.uniform(-90, 90, 3)
    view.lookAt(QVector3D(*eye), QVector3D(*rng.uniform(-5, 5, 3)),
                QVector3D(0, 0, 1))
    return proj * view, eye


def _scene(seed, P, big=False):
    rng = np.random.default_rng(seed)
    protos = [_proto(rng, big) for _ in range(5)]
    of = rng.integers(0, len(protos), P)
    xfs = [_matrix(rng) for _ in range(P)]
    bakes = [_bake(protos[of[i]], xfs[i]) for i in range(P)]
    lo = np.empty((P, 3))
    hi = np.empty((P, 3))
    for i, (v0, e1, e2, ends) in enumerate(bakes):
        pts = np.concatenate([v0, v0 + e1, v0 + e2, ends.reshape(-1, 3)])
        lo[i], hi[i] = pts.min(axis=0), pts.max(axis=0)
    iset = mod.InstanceSet([mod.InstanceProto(*p) for p in protos],
                           of.astype(np.int64),
                           np.array([m.data() for m in xfs], np.float64),
                           lo, hi)
    return rng, bakes, iset


@pytest.mark.parametrize("seed,big", [(s, False) for s in range(6)]
                         + [(s, True) for s in range(100, 103)])
def test_corners_near_are_the_baked_ends_at_their_pixels(seed, big):
    from views.viewport import Viewport
    rng, bakes, iset = _scene(seed, 40 if big else 120, big)
    P = len(bakes)
    found_any = 0
    for _ in range(12):
        mvp, _eye = _camera(rng)
        eye = _Eye(mvp)
        colmajor = list(mvp.data())
        for _k in range(8):
            px, py = rng.uniform(0, W), rng.uniform(0, H)
            reach = float(rng.choice([8.0, 40.0, 200.0]))
            want = set()
            for i in range(P):
                ends = bakes[i][3]
                if not len(ends):
                    continue
                ax, ay, oka = Viewport._project_px(eye, ends[:, 0])
                bx, by, okb = Viewport._project_px(eye, ends[:, 1])
                ok = oka & okb
                for end, (sx, sy) in enumerate(((ax, ay), (bx, by))):
                    dx, dy = sx - px, sy - py
                    near = ok & (dx * dx + dy * dy <= reach * reach)
                    for e in np.flatnonzero(near):
                        want.add((i, int(e), end, *ends[e, end].tolist(),
                                  float(sx[e]), float(sy[e])))
            cand = rng.permutation(P).astype(np.int64)
            pl, ed, en, xyz, sx, sy = iset.corners_near(
                cand, colmajor, float(W), float(H), px, py, reach)
            got = {(int(a), int(b), int(c), *x.tolist(), float(u), float(v))
                   for a, b, c, x, u, v in zip(pl, ed, en, xyz, sx, sy)}
            assert got == want
            # In the order of ``cand``.
            pos = {int(i): k for k, i in enumerate(cand)}
            assert all(pos[int(a)] <= pos[int(b)] for a, b in zip(pl, pl[1:]))
            found_any += len(got)
    assert found_any > 50


def _hidden_by(v0, e1, e2, o, d, limit):
    """``Viewport._occluded_many``'s NumPy block, for one ray."""
    if not len(v0):
        return False
    s = o - v0
    q = np.cross(s, e1)
    uq = np.einsum("ij,ij->i", e2, q)
    dd = d[None, :]
    p = np.cross(dd[:, None, :], e2[None, :, :])
    det = np.einsum("nj,rnj->rn", e1, p)
    ok = np.abs(det) > 1e-6
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    u = np.einsum("nj,rnj->rn", s, p) * inv
    v = (dd @ q.T) * inv
    t = uq[None, :] * inv
    hit = (ok & (u >= 0.0) & (u <= 1.0) & (v >= 0.0) & (u + v <= 1.0)
           & (t > 1e-6))
    return bool(np.where(hit, t, np.inf).min() < limit)


@pytest.mark.parametrize("seed", range(6))
def test_occluded_is_the_baked_answer_and_doubts_settle_on_ray_tris(seed):
    rng, bakes, iset = _scene(50 + seed, 150)
    P = len(bakes)
    allv0 = np.concatenate([b[0] for b in bakes])
    alle1 = np.concatenate([b[1] for b in bakes])
    alle2 = np.concatenate([b[2] for b in bakes])
    cand = np.arange(P, dtype=np.int64)
    hidden_n = doubt_n = 0
    for _ in range(10):
        # An eye among the copies: many of them hide one another.
        o = rng.uniform(-15, 15, 3)
        pts = []
        for _k in range(40):
            v0, e1, _e2, ends = bakes[int(rng.integers(P))]
            r = int(rng.integers(len(v0)))
            # Corners (on their own faces), and points inside triangles.
            c = v0[r] + (e1[r] + _e2[r]) / 3.0
            k = rng.random()
            if k < 0.4:
                pts.append(c + (c - o) * rng.uniform(0.01, 0.5))  # behind
            elif k < 0.6 and len(ends):
                pts.append(ends[0, 0])
            else:
                pts.append(v0[r] + e1[r] * rng.random() * 0.5)
        delta = np.array(pts) - o
        dist = np.linalg.norm(delta, axis=1)
        D = delta / dist[:, None]
        limit = dist - 1e-3
        hid, dbt = iset.occluded(cand, tuple(o), np.ascontiguousarray(D),
                                 limit)
        for r in range(len(pts)):
            want = _hidden_by(allv0, alle1, alle2, o, D[r], limit[r])
            if dbt[r]:
                doubt_n += 1
                a, b, c = iset.ray_tris(cand, tuple(o), tuple(D[r]),
                                        float(limit[r]))
                assert _hidden_by(a, b, c, o, D[r], limit[r]) == want
            else:
                assert bool(hid[r]) == want, r
            hidden_n += want
    assert hidden_n > 20
    assert doubt_n < 40


@pytest.mark.parametrize("seed", range(4))
def test_corners_the_frame_hides_are_left_out_as_python_leaves_them(seed):
    """``corners_near`` with the frame's depth limits drops exactly the
    corners ``Viewport._depth_hidden`` would drop from its full answer."""
    from views.viewport import Viewport
    rng, bakes, iset = _scene(200 + seed, 120)
    P = len(bakes)
    cand = np.arange(P, dtype=np.int64)
    dropped = 0
    for _ in range(10):
        mvp, eye = _camera(rng)
        colmajor = list(mvp.data())
        px, py = rng.uniform(100, W - 100), rng.uniform(100, H - 100)
        reach = 40.0
        dpr = float(rng.choice([1.0, 2.0]))
        x0 = int(np.floor((px - reach) * dpr)) - 1
        y0 = int(H * dpr) - 1 - (int(np.floor((py + reach) * dpr)) + 1)
        gw = gh = int(2 * reach * dpr) + 4
        dist = np.linalg.norm(eye)
        lim = rng.uniform(dist * 0.5, dist * 1.5, (gh, gw))
        lim[rng.random((gh, gw)) < 0.2] = np.inf
        seen = (list(map(float, eye)), np.ascontiguousarray(lim), x0, y0,
                dpr, int(H * dpr))
        full = iset.corners_near(cand, colmajor, float(W), float(H), px, py,
                                 reach)
        pl, ed, en, xyz, sx, sy = full
        keep = ~Viewport._depth_hidden(seen, xyz, sx, sy)
        want = {(int(a), int(b), int(c)) for a, b, c, k
                in zip(pl, ed, en, keep) if k}
        got = iset.corners_near(cand, colmajor, float(W), float(H), px, py,
                                reach, seen)
        assert {(int(a), int(b), int(c))
                for a, b, c in zip(got[0], got[1], got[2])} == want
        dropped += int((~keep).sum())
    assert dropped > 10


@pytest.mark.parametrize("seed,limits", [(s, k) for s in range(3)
                                         for k in ("near", "split", "far")])
def test_boxes_behind_the_frame_are_left_out_whole(seed, limits):
    """Big prototypes (their edges in a BVH) under limits that hide whole
    branches: what ``corners_near`` leaves out, box by box, is exactly what
    ``_depth_hidden`` drops corner by corner — the same corners, in the
    same order, coordinates and pixels."""
    from views.viewport import Viewport
    rng, bakes, iset = _scene(500 + seed, 40, big=True)
    cand = np.arange(len(bakes), dtype=np.int64)
    dropped = kept = 0
    for _ in range(12):
        mvp, eye = _camera(rng)
        colmajor = list(mvp.data())
        px, py = rng.uniform(150, W - 150), rng.uniform(150, H - 150)
        reach = float(rng.choice([10.0, 40.0]))
        dpr = float(rng.choice([1.0, 1.5, 2.0]))
        x0 = int(np.floor((px - reach) * dpr)) - 1
        y0 = int(H * dpr) - 1 - (int(np.floor((py + reach) * dpr)) + 1)
        gw = gh = int(2 * reach * dpr) + 4
        dist = np.linalg.norm(eye)
        if limits == "near":              # a wall close in front: all hidden
            lim = rng.uniform(dist * 0.2, dist * 0.4, (gh, gw))
        elif limits == "split":           # a wall over half the patch
            lim = np.full((gh, gw), dist * 3.0)
            lim[:, : gw // 2] = dist * rng.uniform(0.3, 1.0)
        else:                              # the scene's own depth, roughly
            lim = np.full((gh, gw), dist * rng.uniform(0.8, 1.2))
        seen = (list(map(float, eye)), np.ascontiguousarray(lim), x0, y0,
                dpr, int(H * dpr))
        full = iset.corners_near(cand, colmajor, float(W), float(H), px, py,
                                 reach)
        keep = ~Viewport._depth_hidden(seen, full[3], full[4], full[5])
        got = iset.corners_near(cand, colmajor, float(W), float(H), px, py,
                                reach, seen)
        for a, b in zip(full, got):
            assert np.array_equal(a[keep], b)
        dropped += int((~keep).sum())
        kept += int(keep.sum())
    assert dropped > 100
    if limits != "near":
        assert kept > 20


@pytest.mark.parametrize("seed,big", [(s, False) for s in range(6)]
                         + [(s, True) for s in range(400, 403)])
def test_edges_near_are_the_baked_edges_at_their_distances(seed, big):
    """``edges_near`` gives the hard edges of the bakes within the radius at
    the distance ``segment_distances`` measures on ``_project_px``'s pixels,
    bit for bit, the nearest ``cap`` of them, nearest first."""
    from core.edge_grid import segment_distances
    from views.viewport import Viewport
    rng, bakes, iset = _scene(300 + seed, 40 if big else 120, big)
    P = len(bakes)
    found = 0
    for _ in range(12):
        mvp, _eye = _camera(rng)
        eye = _Eye(mvp)
        colmajor = list(mvp.data())
        for _k in range(6):
            px, py = rng.uniform(0, W), rng.uniform(0, H)
            radius = float(rng.choice([8.0, 48.0, 64.0]))
            cap = int(rng.choice([1, 48, 10 ** 6]))
            cand = rng.permutation(P).astype(np.int64)
            pos = {int(i): k for k, i in enumerate(cand)}
            want = []
            for i in range(P):
                ends = bakes[i][3]
                if not len(ends):
                    continue
                ax, ay, oka = Viewport._project_px(eye, ends[:, 0])
                bx, by, okb = Viewport._project_px(eye, ends[:, 1])
                d = segment_distances(ax, ay, bx, by, oka & okb, px, py)
                for e in np.flatnonzero(d < radius):
                    want.append((float(d[e]), pos[i], int(e), i,
                                 *ends[e, 0].tolist(), *ends[e, 1].tolist()))
            want.sort(key=lambda t: t[:3])
            want = [(t[3], t[2], *t[4:], t[0]) for t in want[:cap]]
            pl, ed, a, b, d = iset.edges_near(cand, colmajor, float(W),
                                              float(H), px, py, radius, cap)
            got = [(int(p), int(e), *aa.tolist(), *bb.tolist(), float(dd))
                   for p, e, aa, bb, dd in zip(pl, ed, a, b, d)]
            assert got == want
            found += len(got)
    assert found > 50


@pytest.mark.parametrize("seed", range(4))
def test_boxes_near_px_is_the_numpy_footprint(seed):
    """``boxes_near_px`` keeps the boxes ``_placements_under_px`` keeps:
    near the pixel, crossing the eye plane, or not finite."""
    from views.viewport import Viewport
    if not hasattr(mod, "boxes_near_px"):
        pytest.skip("older module")
    rng = np.random.default_rng(700 + seed)
    P = 3000
    c = rng.uniform(-80, 80, (P, 3))
    s = rng.uniform(0.01, 6, (P, 3))
    lo, hi = c - s, c + s
    lo[rng.random(P) < 0.01, 0] = -np.inf
    for _ in range(10):
        mvp, _eye = _camera(rng)
        eye = _Eye(mvp)
        eye._PICK_NEAR_PX = Viewport._PICK_NEAR_PX
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = float(rng.choice([32.0, 48.0]))
        keep, _native.native = _native.native, None      # the NumPy path
        try:
            want = Viewport._placements_under_px(eye, lo, hi, x, y, r)
        finally:
            _native.native = keep
        got = mod.boxes_near_px(lo, hi, np.ascontiguousarray(eye._m).ravel()
                                .tolist(), float(W), float(H), x, y, r)
        assert np.array_equal(np.asarray(got), np.asarray(want))
