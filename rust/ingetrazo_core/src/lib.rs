// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
//! Native kernels for IngeTrazo. Optional: `core/_native.py` imports this
//! module when it is built and falls back to the Python code otherwise.
//!
//! Every kernel here mirrors a Python function line by line — the same
//! arithmetic in the same order — so both give the same drawing. The only
//! thing a kernel may add is an index that finds the SAME candidates faster.

use numpy::{PyArray1, PyArray2, PyReadonlyArray2, PyReadonlyArray3, PyReadonlyArray1};
use pyo3::prelude::*;

mod boxes;
mod hlr;
mod parity;

#[pymodule]
fn ingetrazo_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<HlrOccluders>()?;
    m.add_function(wrap_pyfunction!(touching_boxes, m)?)?;
    m.add_class::<ParityTris>()?;
    Ok(())
}

/// The triangles of one hidden-line pass, in camera space, with a 2D grid
/// over their bounding boxes. Built once per view by `core.hlr`.
#[pyclass(frozen)]
struct HlrOccluders {
    inner: hlr::Occluders,
}

#[pymethods]
impl HlrOccluders {
    /// ``tc``: (T,3,3) triangle vertices in camera space (x, y, depth).
    #[new]
    fn new(tc: PyReadonlyArray3<'_, f64>) -> PyResult<Self> {
        let tc = tc.as_array();
        let n = tc.shape()[0];
        let mut tris = Vec::with_capacity(n);
        for t in 0..n {
            let mut v = [[0.0f64; 3]; 3];
            for k in 0..3 {
                for c in 0..3 {
                    v[k][c] = tc[[t, k, c]];
                }
            }
            tris.push(v);
        }
        Ok(Self { inner: hlr::Occluders::new(tris) })
    }

    /// Visible t-intervals of every edge: core.hlr.visible_spans for each
    /// row, with the same candidate filter as hlr_drawing. ``a``/``b``:
    /// (E,3) endpoints in camera space. Returns ``(offsets (E+1,), spans
    /// (S,2))``: edge i owns spans[offsets[i]:offsets[i+1]].
    fn visible_spans<'py>(
        &self,
        py: Python<'py>,
        a: PyReadonlyArray2<'_, f64>,
        b: PyReadonlyArray2<'_, f64>,
        eps: f64,
    ) -> PyResult<(Bound<'py, PyArray1<i64>>, Bound<'py, PyArray2<f64>>)> {
        let a = a.as_array();
        let b = b.as_array();
        let n = a.shape()[0];
        let edges: Vec<([f64; 3], [f64; 3])> = (0..n)
            .map(|i| {
                ([a[[i, 0]], a[[i, 1]], a[[i, 2]]], [b[[i, 0]], b[[i, 1]], b[[i, 2]]])
            })
            .collect();
        let inner = &self.inner;
        let (offsets, spans) = py.detach(|| inner.visible_spans_all(&edges, eps));
        let flat: Vec<Vec<f64>> = spans.iter().map(|s| vec![s.0, s.1]).collect();
        let off = PyArray1::from_vec(py, offsets);
        let sp = if flat.is_empty() {
            PyArray2::zeros(py, [0, 2], false)
        } else {
            PyArray2::from_vec2(py, &flat)?
        };
        Ok((off, sp))
    }

    /// The Profiles test of hlr_drawing for many visible spans at once:
    /// for each row, is the background on either side of the span's
    /// midpoint? ``mid`` (N,2), ``nrm`` (N,2) the sideways probe offset,
    /// ``zm`` (N,) the span's depth at the midpoint.
    fn profile_flags<'py>(
        &self,
        py: Python<'py>,
        mid: PyReadonlyArray2<'_, f64>,
        nrm: PyReadonlyArray2<'_, f64>,
        zm: PyReadonlyArray1<'_, f64>,
        delta: f64,
        ptol: f64,
    ) -> PyResult<Bound<'py, PyArray1<bool>>> {
        let mid = mid.as_array();
        let nrm = nrm.as_array();
        let zm = zm.as_array();
        let n = mid.shape()[0];
        let probes: Vec<([f64; 2], [f64; 2], f64)> = (0..n)
            .map(|i| ([mid[[i, 0]], mid[[i, 1]]], [nrm[[i, 0]], nrm[[i, 1]]], zm[i]))
            .collect();
        let inner = &self.inner;
        let out = py.detach(|| inner.profile_flags(&probes, delta, ptol));
        Ok(PyArray1::from_vec(py, out))
    }
}

fn rows3(a: &numpy::ndarray::ArrayView2<'_, f64>) -> Vec<[f64; 3]> {
    (0..a.shape()[0]).map(|i| [a[[i, 0]], a[[i, 1]], a[[i, 2]]]).collect()
}

/// core.intersect._touching for all rows at once: the index pairs ``(i,
/// j)`` whose boxes touch (within ``eps``), sorted by i then j; ``same``:
/// j > i only. ``lo_*``/``hi_*``: (N,3) box corners.
#[pyfunction]
fn touching_boxes<'py>(
    py: Python<'py>,
    lo_a: PyReadonlyArray2<'_, f64>,
    hi_a: PyReadonlyArray2<'_, f64>,
    lo_b: PyReadonlyArray2<'_, f64>,
    hi_b: PyReadonlyArray2<'_, f64>,
    same: bool,
    eps: f64,
) -> PyResult<(Bound<'py, PyArray1<i64>>, Bound<'py, PyArray1<i64>>)> {
    let a: Vec<boxes::Box3> = rows3(&lo_a.as_array()).into_iter()
        .zip(rows3(&hi_a.as_array())).collect();
    let b: Vec<boxes::Box3> = rows3(&lo_b.as_array()).into_iter()
        .zip(rows3(&hi_b.as_array())).collect();
    let (ii, jj) = py.detach(|| boxes::touching(&a, &b, same, eps));
    Ok((PyArray1::from_vec(py, ii), PyArray1::from_vec(py, jj)))
}

/// A packed triangle set (core.orient._PackedTris) with a ray index, for
/// the parity queries of orientation and of the push/pull rebuild.
#[pyclass(frozen)]
struct ParityTris {
    inner: parity::Tris,
}

#[pymethods]
impl ParityTris {
    /// ``a``/``e1``/``e2``: (N,3) vertex A and the two edge vectors;
    /// ``face_idx``: (N,) the face of each triangle.
    #[new]
    fn new(
        a: PyReadonlyArray2<'_, f64>,
        e1: PyReadonlyArray2<'_, f64>,
        e2: PyReadonlyArray2<'_, f64>,
        face_idx: PyReadonlyArray1<'_, i64>,
    ) -> PyResult<Self> {
        let face = face_idx.as_array().to_vec();
        Ok(Self { inner: parity::Tris::new(rows3(&a.as_array()), rows3(&e1.as_array()),
                                           rows3(&e2.as_array()), face) })
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }

    /// Crossings ahead of ``origin`` (3,) along each row of ``dirs`` (R,3),
    /// over the triangles with ``mask`` True (all when None) that are not of
    /// face ``skip``. Returns a list of R ints.
    #[pyo3(signature = (origin, dirs, mask=None, skip=None))]
    fn crossings(
        &self,
        py: Python<'_>,
        origin: (f64, f64, f64),
        dirs: PyReadonlyArray2<'_, f64>,
        mask: Option<PyReadonlyArray1<'_, bool>>,
        skip: Option<i64>,
    ) -> PyResult<Vec<i64>> {
        let d = rows3(&dirs.as_array());
        let m: Option<Vec<bool>> = mask.map(|m| m.as_array().to_vec());
        if let Some(ref mm) = m {
            if mm.len() != self.inner.len() {
                return Err(pyo3::exceptions::PyValueError::new_err("mask length"));
            }
        }
        let inner = &self.inner;
        let o = [origin.0, origin.1, origin.2];
        Ok(py.detach(|| inner.crossings(o, &d, m.as_deref(), skip)))
    }
}
