# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Dialogs out of their trays, in windows of their own
(views/tray_window.DialogWindow): a header let go where no tray takes it
— several side by side on a second screen, one dropped into another to
keep them together — and back in the trays they came from by the window's
button, by closing it, or by dragging them back."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import QApplication

from core.tray_layout import is_float

_app = QApplication.instance() or QApplication([])

_KEYS = ("ui/tray_layout", "ui/dialog_windows", "ui/hidden_trays",
         "ui/known_trays", "ui/window_state", "ui/tray_windows")


@pytest.fixture(autouse=True)
def _own_settings():
    st = QSettings()
    before = {k: st.value(k) for k in _KEYS if st.contains(k)}
    for k in _KEYS:
        st.remove(k)
    yield
    for k in _KEYS:
        st.remove(k)
    for k, v in before.items():
        st.setValue(k, v)


def _settle():
    for _ in range(5):
        _app.processEvents()


def _window():
    from views.main_window import MainWindow
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    _settle()
    return win


def _close(win):
    win._saved_version = win.viewport.scene.version
    win.close()
    _settle()


def _keys(stack):
    return [s.key for s in stack.sections()]


def test_a_dialog_let_go_out_of_the_trays_becomes_a_window_of_its_own():
    from views.tray_window import DialogWindow
    win = _window()
    try:
        manager = win.tray_manager
        at = QPoint(120, 140)
        dw = manager.float_section("entity_info", at)
        _settle()
        assert isinstance(dw, DialogWindow) and dw.isVisible()
        assert _keys(dw.stack) == ["entity_info"]
        assert "entity_info" not in _keys(win.tray.widget())
        assert is_float(manager.layout.tray_of("entity_info"))
        assert dw.windowTitle() == "Entity info" == dw.bar.name()
        assert dw.pos() + dw.stack_offset() == at       # header under it
        assert dw.windowFlags() & Qt.FramelessWindowHint
        assert "trays they came from" in dw.bar.dock_btn.toolTip()
    finally:
        _close(win)


def test_several_dialogs_side_by_side_or_together_in_one_window():
    win = _window()
    try:
        manager = win.tray_manager
        layers = manager.float_section("layers", QPoint(50, 50))
        scenes = manager.float_section("scenes", QPoint(450, 50))
        _settle()
        assert layers is not scenes and len(manager.floats) == 2
        before = layers.height()
        manager.place("scenes", layers.tray, 1)           # dropped into it
        _settle()
        assert _keys(layers.stack) == ["layers", "scenes"]
        assert layers.height() > before                   # room for it
        assert len(manager.floats) == 1                   # the other went
        assert layers.windowTitle() == "Layers · Scenes"
    finally:
        _close(win)


def test_putting_dialogs_back_returns_each_where_it_came_from():
    win = _window()
    try:
        manager = win.tray_manager
        mine = manager.new_tray("Mine")
        manager.set_section(mine, "layers", True)
        out = manager.float_section("layers")             # from «Mine»
        manager.float_section("materials")                # from Properties
        manager.place("materials", out.tray, 1)           # together
        out.bar.dock_btn.click()                          # put back
        _settle()
        assert manager.floats == {}
        assert manager.layout.float_trays() == []
        assert _keys(manager.docks[mine].widget()) == ["layers"]
        assert "materials" in _keys(win.tray.widget())
    finally:
        _close(win)


def test_the_last_dialog_dragged_back_into_a_tray_closes_its_window():
    win = _window()
    try:
        manager = win.tray_manager
        manager.float_section("base_map")
        manager.place("base_map", "tray_georef", 0)
        _settle()
        assert manager.floats == {} and manager.layout.float_trays() == []
        assert _keys(win.georef_tray.widget())[0] == "base_map"
    finally:
        _close(win)


def test_a_header_let_go_where_no_tray_takes_it_floats_the_dialog():
    """What a header dragged out of the window and let go does."""
    win = _window()
    try:
        stack = win.tray.widget()
        stack.floatRequested.emit("parts", QPoint(60, 70))
        _settle()
        dw = win.tray_manager.host_of("parts")
        assert dw is not None and dw.tray in win.tray_manager.floats
        # Alone in its window, dragged out again: the window moves.
        dw.stack.floatRequested.emit("parts", QPoint(300, 200))
        _settle()
        assert len(win.tray_manager.floats) == 1
        assert dw.pos() + dw.stack_offset() == QPoint(300, 200)
    finally:
        _close(win)


def test_closing_a_dialog_window_puts_its_dialogs_back():
    win = _window()
    try:
        dw = win.tray_manager.float_section("scenes")
        dw.close()                                        # Alt+F4
        _settle()
        assert win.tray_manager.floats == {}
        assert "scenes" in _keys(win.tray.widget())
    finally:
        _close(win)


def test_the_dialog_windows_are_out_again_at_the_next_start():
    win = _window()
    dw = win.tray_manager.float_section("entity_info", QPoint(200, 150))
    dw.resize(333, 444)
    _settle()
    rect = (dw.x(), dw.y(), dw.width(), dw.height())
    _close(win)
    win = _window()
    try:
        _settle()
        floats = list(win.tray_manager.floats.values())
        assert len(floats) == 1
        dw = floats[0]
        assert dw.isVisible() and _keys(dw.stack) == ["entity_info"]
        assert (dw.x(), dw.y(), dw.width(), dw.height()) == rect
        dw.bar.dock_btn.click()                           # and back
        _settle()
        assert "entity_info" in _keys(win.tray.widget())
    finally:
        _close(win)


def test_the_clean_screen_hides_the_dialog_windows_and_brings_them_back():
    win = _window()
    try:
        dw = win.tray_manager.float_section("layers")
        _settle()
        win._toggle_clean_screen(True)
        assert not dw.isVisible()
        win._toggle_clean_screen(False)
        _settle()
        assert dw.isVisible()
    finally:
        _close(win)


def test_the_trays_file_carries_the_dialog_windows():
    import json
    from views.manage_trays import export_trays, import_trays
    win = _window()
    try:
        manager = win.tray_manager
        dw = manager.float_section("materials", QPoint(400, 300))
        _settle()
        data = json.loads(json.dumps(export_trays(win)))
        assert dw.tray in data["dialog_windows"]
        manager.put_back(dw.tray)
        assert manager.floats == {}
        import_trays(win, data)
        _settle()
        back = manager.host_of("materials")
        assert back in manager.floats.values() and back.isVisible()
    finally:
        _close(win)


def test_manage_trays_puts_a_dialog_out_in_a_window_back_in_a_tray():
    from views.manage_trays import ManageTraysDialog
    win = _window()
    try:
        manager = win.tray_manager
        manager.float_section("survey")
        dialog = ManageTraysDialog(win, manager, select="tray_georef")
        check = dialog.checks["survey"]
        assert not check.isChecked()
        assert "window of its own" in check.toolTip()
        check.setChecked(True)
        _settle()
        assert manager.floats == {}
        assert "survey" in _keys(win.georef_tray.widget())
        dialog.deleteLater()
    finally:
        _close(win)


def test_a_panel_out_in_a_window_is_brought_forward_there():
    """The Browser — or an extension's panel, asked for by its extension —
    out in a window: showing it shows that window."""
    win = _window()
    try:
        manager = win.tray_manager
        dw = manager.float_section("browser")
        _settle()
        assert dw is manager.host_of("browser")
        assert win.project_browser.outliner.window() is dw
        dw.hide()
        assert manager.show_dialog("browser") and dw.isVisible()
    finally:
        _close(win)
