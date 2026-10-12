# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Window ▸ Manage Trays (SketchUp's): trays of your own as new tabs of the
side bar, the sections each tray shows checked in a dialog, the sections
of a tray reordered by dragging their framed header — and all of it the
same at the next start."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDockWidget

from core.tray_layout import DEFAULT_SECTIONS, TrayLayout, all_sections

_app = QApplication.instance() or QApplication([])

#: What these tests write to the settings, put back as it was after each:
#: a tray made here must not show up in another test's window.
_KEYS = ("ui/tray_layout", "ui/hidden_trays", "ui/known_trays",
         "ui/window_state")


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


def _window():
    from views.main_window import MainWindow
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    _app.processEvents()
    return win


def _close(win):
    win._saved_version = win.viewport.scene.version
    win.close()
    _app.processEvents()


def _dock_of(widget):
    while widget is not None and not isinstance(widget, QDockWidget):
        widget = widget.parentWidget()
    return widget


def _keys(dock):
    return [s.key for s in dock.widget().sections()]


# ---- the layout, as data ----------------------------------------------------

def test_the_factory_layout_is_the_trays_as_they_were():
    layout = TrayLayout()
    assert layout.trays == {t: list(s) for t, s in DEFAULT_SECTIONS.items()}
    assert layout.tray_of("materials") == "tray_properties"
    assert layout.custom_trays() == []


def test_a_section_is_in_one_tray_at_a_time():
    layout = TrayLayout()
    mine = layout.new_tray("Mine")
    layout.set_section(mine, "entity_info", True)
    layout.set_section(mine, "base_map", True)
    assert layout.trays[mine] == ["entity_info", "base_map"]
    assert "entity_info" not in layout.trays["tray_properties"]
    assert layout.trays["tray_georef"] == ["survey"]
    layout.set_section(mine, "base_map", False)         # unchecked: in none
    assert layout.tray_of("base_map") is None


def test_place_counts_the_index_without_the_moved_section():
    layout = TrayLayout()
    layout.place("entity_info", "tray_properties", 1)   # one down
    assert layout.trays["tray_properties"][:3] == ["layers", "entity_info",
                                                  "scenes"]
    layout.place("parts", "tray_properties", 0)         # to the top
    assert layout.trays["tray_properties"][0] == "parts"
    layout.place("bim", "tray_properties", 99)          # clamped, moved over
    assert layout.trays["tray_properties"][-1] == "bim"
    assert layout.trays["tray_bim"] == []


def test_deleting_a_tray_sends_its_sections_home_to_their_factory_place():
    layout = TrayLayout()
    mine = layout.new_tray("Mine")
    for s in ("materials", "survey", "entity_info"):
        layout.set_section(mine, s, True)
    assert layout.delete(mine) == ["materials", "survey", "entity_info"]
    assert layout.trays == {t: list(s) for t, s in DEFAULT_SECTIONS.items()}
    assert mine not in layout.names
    with pytest.raises(KeyError):
        layout.delete("tray_properties")             # built-in: stays
    with pytest.raises(KeyError):
        layout.rename("tray_bim", "x")


def test_the_layout_reads_back_what_it_saved():
    layout = TrayLayout()
    mine = layout.new_tray("Mi bandeja")
    layout.set_section(mine, "layers", True)
    layout.set_section("tray_properties", "scenes", False)
    layout.place("parts", "tray_properties", 0)
    again = TrayLayout.from_json(layout.to_json())
    assert again.trays == layout.trays
    assert again.names == {mine: "Mi bandeja"}
    assert again.tray_of("scenes") is None             # still taken out


def test_a_damaged_or_foreign_layout_is_read_as_far_as_it_makes_sense():
    factory = TrayLayout().trays
    for junk in (None, "", "{", "[]", '{"trays": 3}', b"\xff"):
        assert TrayLayout.from_json(junk).trays == factory
    text = ('{"trays": ['
            '{"id": "tray_properties", "sections": ["parts", "nope", "parts", 7]},'
            '{"id": "tray_from_the_future", "sections": ["layers"]},'
            '{"id": "tray_user_1", "sections": ["layers"]},'          # no name
            '{"id": "tray_user_2", "name": "Mine", "sections": ["bim"]}],'
            '"known": ["parts", "layers", "bim", {"x": 1}]}')
    layout = TrayLayout.from_json(text)
    assert layout.custom_trays() == ["tray_user_2"]
    assert layout.trays["tray_user_2"] == ["bim"]
    assert layout.tray_of("layers") is None          # known, placed nowhere
    # Sections this save did not know yet start in their own trays, at
    # their factory place around the ones it kept.
    assert layout.trays["tray_properties"] == [
        "entity_info", "scenes", "materials", "components", "parts"]
    assert layout.tray_of("base_map") == "tray_georef"
    assert sorted(s for t in layout.trays.values() for s in t) == \
        sorted(set(all_sections()) - {"layers"})


def test_a_new_tray_never_takes_a_deleted_ones_name():
    layout = TrayLayout()
    first = layout.new_tray("A")
    layout.delete(first)
    assert layout.new_tray("A") != first


# ---- in the window ----------------------------------------------------------

def test_the_window_menu_and_the_tab_menu_offer_manage_trays(monkeypatch):
    win = _window()
    try:
        window_menu = next(a.menu() for a in win.menuBar().actions()
                           if a.menu() is not None
                           and a.menu().title() == "Window")
        assert "Manage Trays…" in [a.text() for a in window_menu.actions()]

        win._style_dock_tabs()
        _app.processEvents()
        # Qt keeps spare tab bars around, out of sight: the one on screen.
        bar = next(tb for tb in win._dock_tab_bars()
                   if tb.isVisible() and tb.count()
                   and win.rect().contains(tb.geometry()))
        at = bar.mapTo(win, bar.tabRect(0).center())
        assert win._tray_tab_bar_at(at)
        menu = win._tray_tab_menu(at)
        entry = next(a for a in menu.actions() if a.text() == "Manage Trays…")
        opened = []
        monkeypatch.setattr(win, "open_manage_trays", opened.append)
        entry.trigger()
        assert opened == [win._dock_tab_at(at).objectName()]
    finally:
        _close(win)


def test_a_new_tray_is_a_tab_that_takes_the_sections_checked_for_it():
    win = _window()
    try:
        manager = win.tray_manager
        mine = manager.new_tray("Mine")
        _app.processEvents()
        dock = manager.docks[mine]
        assert dock in win._sidebar_docks() and dock.windowTitle() == "Mine"
        assert dock.isVisible()
        manager.set_section(mine, "entity_info", True)
        manager.set_section(mine, "survey", True)
        assert _dock_of(win.tray.entity_info) is dock
        assert _dock_of(win.georef_tray.survey) is dock
        assert "entity_info" not in _keys(win.tray)
        # The panel is the same one, still refreshed by its own tray.
        win.tray.on_scene_changed()
        manager.set_section(mine, "survey", False)          # in no tray
        assert _dock_of(win.georef_tray.survey) is None
        assert not win.georef_tray.survey.isVisible()
    finally:
        _close(win)


def test_trays_and_their_sections_are_the_same_at_the_next_start():
    win = _window()
    manager = win.tray_manager
    mine = manager.new_tray("Mine")
    manager.set_section(mine, "materials", True)
    manager.place("parts", "tray_properties", 0)
    manager.set_section("tray_properties", "scenes", False)
    _close(win)
    win = _window()
    try:
        dock = win.tray_manager.docks[mine]
        assert dock.objectName() == mine and dock.windowTitle() == "Mine"
        assert _keys(dock) == ["materials"]
        assert _keys(win.tray) == ["parts", "entity_info", "layers",
                                   "components"]
        assert _dock_of(win.tray.scenes) is None
    finally:
        _close(win)


def test_deleting_a_tray_removes_its_tab_and_gives_its_sections_back():
    win = _window()
    try:
        manager = win.tray_manager
        mine = manager.new_tray("Mine")
        manager.set_section(mine, "layers", True)
        dock = manager.docks[mine]
        win._left_was = [dock]              # folded away on the left side
        manager.delete(mine)
        _app.processEvents()
        assert dock not in win._sidebar_docks()
        assert win._left_was == []          # unfolding won't bring it back
        assert _keys(win.tray) == list(DEFAULT_SECTIONS["tray_properties"])
        assert mine not in TrayLayout.from_json(
            QSettings().value("ui/tray_layout")).trays
    finally:
        _close(win)


def test_the_dialog_checks_the_sections_of_the_selected_tray(monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from views.manage_trays import ManageTraysDialog
    win = _window()
    try:
        dialog = ManageTraysDialog(win, win.tray_manager,
                                   select="tray_georef")
        assert dialog.current_tray() == "tray_georef"
        on = {k for k, c in dialog.checks.items() if c.isChecked()}
        assert on == {"base_map", "survey"}
        assert not dialog.rename_btn.isEnabled()        # built-in tray
        assert not dialog.delete_btn.isEnabled()

        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("Site", True)))
        dialog._on_new()
        mine = dialog.current_tray()
        assert win.tray_manager.title(mine) == "Site"
        assert not any(c.isChecked() for c in dialog.checks.values())
        assert dialog.rename_btn.isEnabled() and dialog.delete_btn.isEnabled()
        dialog.checks["base_map"].setChecked(True)      # moved here
        assert _dock_of(win.georef_tray.base_map) is win.tray_manager.docks[mine]
        assert "Site" not in dialog.checks["base_map"].toolTip()

        # A name another tab already has is refused (tabs are told apart
        # by their text).
        warned = []
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: warned.append(a)))
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("properties", True)))
        dialog._on_rename()
        assert warned and win.tray_manager.title(mine) == "Site"
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("Obra", True)))
        dialog._on_rename()
        assert win.tray_manager.docks[mine].windowTitle() == "Obra"

        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Yes))
        dialog._on_delete()
        assert mine not in win.tray_manager.docks
        assert _dock_of(win.georef_tray.base_map) is win.georef_tray
        dialog.deleteLater()
    finally:
        _close(win)


def test_a_section_header_menu_moves_it_up_and_down():
    win = _window()
    try:
        stack = win.tray.widget()
        layers = next(s for s in stack.sections() if s.key == "layers")
        menu = stack.section_menu(layers)
        up, down = menu.actions()[:2]
        up.trigger()
        assert _keys(win.tray)[:2] == ["layers", "entity_info"]
        menu = stack.section_menu(layers)
        assert not menu.actions()[0].isEnabled()        # already on top
        menu.actions()[1].trigger()
        assert _keys(win.tray)[:2] == ["entity_info", "layers"]
        assert "Manage Trays…" in [a.text() for a in menu.actions()]
    finally:
        _close(win)


def test_a_section_dropped_on_a_tray_lands_where_the_line_shows():
    win = _window()
    try:
        stack = win.tray.widget()
        for s in stack.sections():
            s._btn.setChecked(False)                   # folded: short ones
        _app.processEvents()
        sections = stack.sections()
        parts = sections[-1]
        top = sections[0].y() + 1                       # over Entity info
        stack.drag_over(top)
        assert stack._line.isVisible()
        stack.drop(parts.key, top)
        assert not stack._line.isVisible()
        _app.processEvents()                            # after the drag
        assert _keys(win.tray)[0] == "parts"
        # Dropped where it already is: nothing moves.
        before = _keys(win.tray)
        stack.drop("parts", 1)
        _app.processEvents()
        assert _keys(win.tray) == before
        # From another tray: it moves over.
        stack.drop("bim", stack.widget().height() - 1)
        _app.processEvents()
        assert _keys(win.tray)[-1] == "bim" and _keys(win.bim_tray) == []
        for s in stack.sections():
            s._btn.setChecked(True)
    finally:
        _close(win)


def test_a_section_dragged_over_a_text_field_still_lands_in_the_tray():
    """A text field takes drops of its own and refused this one: while a
    header is dragged, every drag event over a tray goes to its stack."""
    from PySide6.QtCore import QMimeData, Qt
    from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
    from PySide6.QtWidgets import QLineEdit, QWidget
    from views.tray import (SECTION_MIME, SectionStack, _Section,
                            _SectionDropRouter)
    field = QLineEdit()
    first = _Section("First", QWidget(), "first")
    stack = SectionStack([first, _Section("Second", field, "second")])
    stack.resize(300, 400)
    stack.show()
    _app.processEvents()
    moved = []
    stack.sectionMoved.connect(lambda key, index: moved.append((key, index)))
    mime = QMimeData()
    mime.setData(SECTION_MIME, b"first")
    router = _SectionDropRouter()
    _app.installEventFilter(router)
    try:
        at = field.rect().center()          # the lower half of «Second»
        for event in (
                QDragEnterEvent(at, Qt.MoveAction, mime, Qt.LeftButton,
                                Qt.NoModifier),
                QDragMoveEvent(at, Qt.MoveAction, mime, Qt.LeftButton,
                               Qt.NoModifier)):
            _app.sendEvent(field, event)
            assert event.isAccepted()
            assert stack._line.isVisible()
        drop = QDropEvent(at.toPointF(), Qt.MoveAction, mime, Qt.LeftButton,
                          Qt.NoModifier)
        _app.sendEvent(field, drop)
        assert drop.isAccepted() and field.text() == ""
    finally:
        _app.removeEventFilter(router)
        router.finish()
    _app.processEvents()
    assert moved == [("first", 1)]                  # below «Second»
    assert not stack._line.isVisible()
    stack.close()


def test_a_section_header_is_a_framed_strip():
    from views.tray import _Section
    from PySide6.QtWidgets import QWidget
    sheet = _Section("Entity info", QWidget(), "entity_info")._btn.styleSheet()
    assert "border: 1px solid" in sheet and "border-radius" in sheet
    assert "background:" in sheet


def test_bringing_a_panel_forward_finds_the_tray_it_is_in_now():
    win = _window()
    try:
        manager = win.tray_manager
        mine = manager.new_tray("Mine")
        manager.set_section(mine, "base_map", True)
        raised = []
        dock = manager.docks[mine]
        dock.raise_ = lambda: raised.append(dock)
        win._raise_tray_of(win.georef_tray.base_map)
        assert raised == [dock]
    finally:
        _close(win)
