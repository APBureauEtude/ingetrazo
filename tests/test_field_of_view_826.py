# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""#826 (Alvaro Celis): the 3D view's lens could not be changed — 45° fixed —
while the composer frames already offered 10°–120°. Camera ▸ Field of
View… sets it; the document and its scenes keep it."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

if QApplication.instance() is None:
    QApplication([])

from core.saved_views import SavedView  # noqa: E402


def test_field_of_view_is_set_kept_and_reset(tmp_path):
    from views.main_window import MainWindow
    win = MainWindow()
    try:
        cam = win.viewport.camera
        assert win._act_field_of_view.text()
        cam.perspective = True
        eye = cam.eye()
        assert win.set_field_of_view(70.0)
        assert cam.fov_deg == 70.0
        assert (cam.eye() - eye).length() < 1e-6       # the eye stays put
        assert win.set_field_of_view(500.0) and cam.fov_deg == 120.0
        assert win.set_field_of_view(1.0) and cam.fov_deg == 10.0
        win.set_field_of_view(70.0)
        # A scene remembers it.
        view = SavedView.capture("vista", win.viewport.scene, cam)
        assert view.to_dict()["fov"] == 70.0
        # The document keeps it.
        win._saved_version = win.viewport.scene.version
        path = tmp_path / "fov.igz"
        win._do_save(path)
        cam.fov_deg = 45.0
        win._saved_version = win.viewport.scene.version
        assert win.open_path(path)
        assert cam.fov_deg == 70.0
        # Parallel has no angle: refused, nothing changes.
        cam.perspective = False
        assert not win.set_field_of_view(30.0)
        assert cam.fov_deg == 70.0
    finally:
        win._saved_version = win.viewport.scene.version
        win.close()


def test_dialog_slider_and_number_preview_the_same_angle():
    from views.field_of_view_dialog import FieldOfViewDialog
    from views.main_window import MainWindow
    win = MainWindow()
    try:
        cam = win.viewport.camera
        eye = cam.eye()
        dialog = FieldOfViewDialog(
            win, cam.fov_deg, *win.FOV_RANGE, win.set_field_of_view)

        dialog.slider.setValue(70)
        assert dialog.value() == 70.0
        assert cam.fov_deg == 70.0
        assert (cam.eye() - eye).length() < 1e-6

        dialog.spin.setValue(35.0)
        assert dialog.slider.value() == 35
        assert cam.fov_deg == 35.0
    finally:
        win._saved_version = win.viewport.scene.version
        win.close()


def test_cancel_restores_the_angle_before_the_live_preview(monkeypatch):
    from views import field_of_view_dialog
    from views.main_window import MainWindow

    class CancelAfterDragging(field_of_view_dialog.FieldOfViewDialog):
        def exec(self):
            self.slider.setValue(70)
            assert self.parent().viewport.camera.fov_deg == 70.0
            return QDialog.Rejected

    monkeypatch.setattr(field_of_view_dialog, "FieldOfViewDialog",
                        CancelAfterDragging)
    win = MainWindow()
    try:
        assert win.viewport.camera.fov_deg == 45.0
        win._ask_field_of_view()
        assert win.viewport.camera.fov_deg == 45.0
    finally:
        win._saved_version = win.viewport.scene.version
        win.close()
