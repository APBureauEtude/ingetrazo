# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""The side trays out in a window of their own (views/tray_window.py): all
the trays of a side at once, by their title strip — an ordinary window
that can go to a second screen, titled with the tab in front, and back on
its side by its button, by closing it, or by dragging it onto a side."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QMimeData, QSettings, Qt
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

_KEYS = ("ui/tray_windows", "ui/tray_layout", "ui/hidden_trays",
         "ui/known_trays", "ui/window_state", "ui/tray_tabs_bottom")


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


def _right(win):
    return [d for d in win._sidebar_docks()
            if d.parentWidget() is win
            and win.dockWidgetArea(d) == Qt.RightDockWidgetArea]


def _bar_on_screen(win, owner=None):
    owner = owner or win
    return next(tb for tb in win._dock_tab_bars()
                if tb.parent() is owner and tb.isVisible() and tb.count()
                and owner.rect().contains(tb.geometry()))


def test_the_strip_stands_over_all_the_tabs():
    """The user: the strip takes all the trays, every tab — over the tabs
    when they are on top, at the top when they are at the bottom."""
    win = _window()
    try:
        band = win._band_docks[Qt.RightDockWidgetArea]
        assert band.isVisible() and band.band.name() == "Properties"
        bar = _bar_on_screen(win)
        assert band.geometry().bottom() <= bar.geometry().top()     # above
        assert band.width() >= bar.width()                          # across
        win.set_tray_tabs_bottom(True)
        _settle()
        bar = _bar_on_screen(win)
        assert band.geometry().bottom() < win.tray.geometry().top() + 2
        assert bar.geometry().top() > win.tray.geometry().top()     # below
    finally:
        win.set_tray_tabs_bottom(False)
        _close(win)


def test_pressing_the_strip_is_the_strip_s_not_qt_s():
    """Let through, the press went to the tray under the strip, and Qt
    dragged that one tray alone."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    win = _window()
    try:
        band = win.band(Qt.RightDockWidgetArea)
        dragged = []
        win.drag_band = lambda b, press: dragged.append(b)
        at = QPointF(20, band.height() / 2)
        g = QPointF(band.mapToGlobal(at.toPoint()))
        press = QMouseEvent(QEvent.MouseButtonPress, at, g, Qt.LeftButton,
                            Qt.LeftButton, Qt.NoModifier)
        _app.sendEvent(band, press)
        assert press.isAccepted()
        far = QPointF(at.x() + 40, at.y() + 40)
        _app.sendEvent(band, QMouseEvent(
            QEvent.MouseMove, far, QPointF(band.mapToGlobal(far.toPoint())),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        assert dragged == [band]
    finally:
        del win.drag_band
        _close(win)


def test_a_layout_with_the_strip_under_the_trays_puts_it_back_on_top():
    """A layout saved before the strips existed lists the trays only."""
    win = _window()
    try:
        band = win._band_docks[Qt.RightDockWidgetArea]
        win.addDockWidget(Qt.RightDockWidgetArea, band)      # now last
        _settle()
        assert band.y() > win.tray.y()
        order = [win.tray, win.project_browser]
        win._seat_bands_if_needed()
        _settle()
        assert band.y() < win.tray.y()
        assert win.project_browser in win.tabifiedDockWidgets(win.tray)
        from views.tray_window import tab_order
        assert tab_order(win, order) == order                # same order
    finally:
        _close(win)


def test_the_trays_of_a_side_go_out_into_a_window_and_come_back():
    from views.tray_window import TrayWindow
    win = _window()
    try:
        before = _right(win)
        closed = [d for d in before if d.isHidden()]
        assert before and closed                    # BIM, Terrain: closed
        win.band(Qt.RightDockWidgetArea).toggle()   # the strip's button
        tw = win._tray_windows()[Qt.RightDockWidgetArea]
        _settle()
        assert isinstance(tw, TrayWindow) and tw.isVisible()
        assert set(tw.docks()) == set(before)       # the closed ones too
        assert all(d.isHidden() for d in closed)    # …still closed
        assert _right(win) == []
        assert tw.windowTitle() == tw.front().windowTitle()
        assert not win._band_docks[Qt.RightDockWidgetArea].isVisible()
        assert not win._sidebar_handle.isVisible()  # nothing left to fold
        win.dock_back(tw)
        _settle()
        assert set(_right(win)) == set(before)
        assert win._tray_windows() == {}
        assert win.tray in win.tabifiedDockWidgets(win.project_browser)
        assert win._band_docks[Qt.RightDockWidgetArea].isVisible()
    finally:
        _close(win)


def test_closing_the_window_or_a_double_click_on_the_strip():
    win = _window()
    try:
        band = win.band(Qt.RightDockWidgetArea)
        band.mouseDoubleClickEvent(None)            # out
        tw = win._tray_windows()[Qt.RightDockWidgetArea]
        assert win.tray.parentWidget() is tw
        tw.close()                                  # closing puts them back
        _settle()
        assert win.tray.parentWidget() is win
        assert win._tray_windows() == {}
    finally:
        _close(win)


def _mime(win, text):
    data = QMimeData()
    data.setData(win.DOCK_MIME, text.encode("utf-8"))
    return data


def test_a_tray_window_dropped_on_a_side_docks_there():
    win = _window()
    try:
        tw = win.detach_side(Qt.RightDockWidgetArea)
        docks = tw.docks()
        win.drop_on_side(_mime(win, f"window:{int(tw.area.value)}"),
                         Qt.LeftDockWidgetArea)
        _settle()
        assert all(win.dockWidgetArea(d) == Qt.LeftDockWidgetArea
                   for d in docks)
        assert win._tray_windows() == {}
        win.move_side(Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea)
    finally:
        _close(win)


def test_a_tab_dragged_out_of_a_tray_window_docks_alone():
    win = _window()
    try:
        tw = win.detach_side(Qt.RightDockWidgetArea)
        win.drop_on_side(_mime(win, win.project_browser.objectName()),
                         Qt.RightDockWidgetArea)
        _settle()
        assert win.project_browser.parentWidget() is win
        assert win.tray.parentWidget() is tw        # the others stay out
        for d in tw.docks():                        # the last one out…
            win.drop_on_side(_mime(win, d.objectName()),
                             Qt.RightDockWidgetArea)
        win._style_dock_tabs()
        _settle()
        assert win._tray_windows() == {}            # …and the window goes
    finally:
        _close(win)


def test_showing_a_tray_that_is_out_shows_its_window():
    win = _window()
    try:
        tw = win.detach_side(Qt.RightDockWidgetArea)
        tw.hide()
        win.set_tray_shown(win.bim_tray, True)
        assert tw.isVisible() and win.bim_tray.isVisible()
    finally:
        _close(win)


def test_the_clean_screen_hides_the_tray_windows_and_brings_them_back():
    win = _window()
    try:
        tw = win.detach_side(Qt.RightDockWidgetArea)
        win._toggle_clean_screen(True)
        assert not tw.isVisible()
        win._toggle_clean_screen(False)
        _settle()
        assert tw.isVisible() and win.tray.isVisible()
    finally:
        _close(win)


def test_the_tray_windows_are_out_again_at_the_next_start():
    win = _window()
    tw = win.detach_side(Qt.RightDockWidgetArea)
    tw.resize(333, 555)
    _settle()
    size = (tw.width(), tw.height())      # its floor may be taller than 555
    names = {d.objectName() for d in tw.docks()}
    _close(win)
    win = _window()                    # the window's first show brings them
    try:
        _settle()
        tw = win._tray_windows().get(Qt.RightDockWidgetArea)
        assert tw is not None and tw.isVisible()
        assert {d.objectName() for d in tw.docks()} == names
        assert (tw.width(), tw.height()) == size
    finally:
        _close(win)


def test_the_strip_s_menu_offers_the_window_and_the_other_side():
    """Right-click on a tab or a strip. «Move to the left side» used to be
    cleared by the panels list filled after it."""
    win = _window()
    try:
        texts = [a.text() for a in win.band_menu(win.tray).actions()]
        assert "Take the trays out into a window of their own" in texts
        assert "Move to the left side" in texts
        assert "Manage Trays…" in texts
        tw = win.detach_side(Qt.RightDockWidgetArea)
        texts = [a.text() for a in win.band_menu(win.tray).actions()]
        assert "Put the trays back in the main window" in texts
        win.dock_back(tw)
    finally:
        _close(win)


def test_the_trays_file_carries_the_tray_windows():
    import json
    from views.manage_trays import export_trays, import_trays
    win = _window()
    try:
        tw = win.detach_side(Qt.RightDockWidgetArea)
        data = json.loads(json.dumps(export_trays(win)))
        assert data["windows"] and data["windows"][0]["side"] == "right"
        win.dock_back(tw)
        assert win._tray_windows() == {}
        import_trays(win, data)
        _settle()
        assert Qt.RightDockWidgetArea in win._tray_windows()
    finally:
        _close(win)


def test_putting_the_strip_back_on_top_keeps_the_groups_of_tabs():
    """A side may hold two groups of tabs, one over the other: the strip
    goes over both, and they stay two, each as it was."""
    win = _window()
    try:
        band = win._band_docks[Qt.RightDockWidgetArea]
        win.set_tray_shown(win.project_browser, True)
        win.addDockWidget(Qt.RightDockWidgetArea, win.project_browser)
        win.addDockWidget(Qt.RightDockWidgetArea, band)     # strip last
        _settle()
        assert win.project_browser not in win.tabifiedDockWidgets(win.tray)
        top = win.front_tray(Qt.RightDockWidgetArea)      # the upper group's
        assert band.y() > top.y()
        win._seat_bands_if_needed()
        _settle()
        top = win.front_tray(Qt.RightDockWidgetArea)
        assert band.y() < top.y() < win.project_browser.y()
        assert win.project_browser not in win.tabifiedDockWidgets(win.tray)
    finally:
        _close(win)


def _late_panel(win, name="extension_late", title="Late"):
    """An extension's panel made after the window showed — the app loads
    the extensions once it is on screen."""
    from PySide6.QtWidgets import QDockWidget, QLabel, QWidget
    dock = QDockWidget(title, win)
    dock.setObjectName(name)
    dock.setWidget(QLabel(title))
    dock.setTitleBarWidget(QWidget(dock))
    win._register_extension_dock(dock)
    _settle()
    return dock


def test_a_panel_that_loads_after_the_strip_was_seated_joins_its_side():
    """The user's start-up: the strip went back on top as the window
    showed; the extensions loaded after, and the AI panel came back to a
    place of its own above the strip — a second group of tabs."""
    from views.main_window import MainWindow
    win = _window()
    _late_panel(win)
    band = win._band_docks[Qt.RightDockWidgetArea]
    win.addDockWidget(Qt.RightDockWidgetArea, band)  # a layout from before
    _settle()                                        # the strips: it last
    _close(win)                                      # saved so
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    _settle()
    try:
        late = _late_panel(win)                      # loads now
        assert late.isVisible()
        assert win.tray in win.tabifiedDockWidgets(late)   # one group
        assert late.y() > win._band_docks[Qt.RightDockWidgetArea].y()
    finally:
        _close(win)


def test_a_closed_panel_that_loads_late_comes_back_among_the_others():
    """Closed from Window ▸ Panels (the user's way out of the second
    group): shown again later, it is a tab with the others."""
    from views.main_window import MainWindow
    win = _window()
    late = _late_panel(win)
    win.set_tray_shown(late, False)
    band = win._band_docks[Qt.RightDockWidgetArea]
    win.addDockWidget(Qt.RightDockWidgetArea, band)
    _settle()
    _close(win)
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    _settle()
    try:
        late = _late_panel(win)
        assert late.isHidden()                       # still closed
        win.set_tray_shown(late, True)
        _settle()
        assert win.tray in win.tabifiedDockWidgets(late)
    finally:
        _close(win)


def test_the_tray_window_has_a_title_row_of_its_own_without_a_close_cross():
    """The user: the red cross that put the trays back read as closing
    them for good. The window's own row: the tab in front, a button that
    fills the screen, and one that puts the trays back — a window with
    its side filled."""
    from views.tray_window import FloatBar
    win = _window()
    try:
        tw = win.detach_side(Qt.RightDockWidgetArea)
        _settle()
        assert tw.windowFlags() & Qt.FramelessWindowHint
        bar = tw.menuWidget()
        assert isinstance(bar, FloatBar)
        assert bar.name() == tw.front().windowTitle()
        assert "right side" in bar.dock_btn.toolTip()
        bar.dock_btn.click()
        _settle()
        assert win._tray_windows() == {}
        assert win.tray.parentWidget() is win
    finally:
        _close(win)


def test_the_tray_window_fills_its_screen_and_gives_its_size_back():
    """The user: put on a second screen, it had to be sized by hand."""
    win = _window()
    try:
        tw = win.detach_side(Qt.RightDockWidgetArea)
        _settle()
        before = tw.geometry()
        tw.menuWidget().max_btn.click()
        _settle()
        assert tw.is_max()
        assert tw.geometry() == tw.screen().availableGeometry()
        entry = win.tray_window_entries()[0]
        assert entry["maximized"] is True
        assert entry["rect"] == [before.x(), before.y(), before.width(),
                                 before.height()]          # its own size
        tw.menuWidget().max_btn.click()
        _settle()
        assert not tw.is_max() and tw.geometry() == before
    finally:
        _close(win)


def test_a_tray_window_that_filled_its_screen_fills_it_again_next_time():
    win = _window()
    tw = win.detach_side(Qt.RightDockWidgetArea)
    _settle()
    tw.toggle_max()
    _settle()
    _close(win)
    win = _window()
    try:
        _settle()
        tw = win._tray_windows().get(Qt.RightDockWidgetArea)
        assert tw is not None and tw.is_max()
    finally:
        _close(win)
