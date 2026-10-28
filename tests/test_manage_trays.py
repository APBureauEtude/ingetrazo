# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Window ▸ Manage Trays (SketchUp's): trays of your own as new tabs of the
side bar, the sections each tray shows checked in a dialog, the sections
of a tray reordered by dragging their framed header — and all of it the
same at the next start."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QWidget

from core.tray_layout import DEFAULT_SECTIONS, TrayLayout, all_sections

_app = QApplication.instance() or QApplication([])

#: What these tests write to the settings, put back as it was after each:
#: a tray made here must not show up in another test's window.
_KEYS = ("ui/tray_layout", "ui/hidden_trays", "ui/known_trays",
         "ui/window_state", "ui/tray_tabs_bottom", "tray/height")


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
    assert layout.trays["tray_properties"][:3] == ["scenes", "entity_info",
                                                  "materials"]
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
    # A tray or a section this version does not know — an extension's, not
    # loaded yet — is kept for when it turns up.
    assert layout.trays["tray_from_the_future"] == ["layers"]
    # Built-in sections this save did not know yet start in their own
    # trays, at their factory place around the ones it kept.
    assert layout.trays["tray_properties"] == [
        "entity_info", "scenes", "materials", "components", "parts", "nope"]
    assert layout.tray_of("base_map") == "tray_georef"
    assert layout.tray_of("browser") == "tray_project_browser"
    placed = {s for t in layout.trays.values() for s in t}
    assert placed == set(all_sections()) | {"nope"}


def test_an_extension_dialog_goes_where_the_saved_layout_put_it():
    saved = TrayLayout()
    mine = saved.new_tray("Mine")
    saved.register("extension_ai", ("extension_ai",))
    saved.register("extension_render", ("extension_render",))
    saved.set_section(mine, "extension_ai", True)
    saved.set_section("extension_render", "extension_render", False)
    layout = TrayLayout.from_json(saved.to_json())
    assert layout.trays[mine] == ["extension_ai"]       # kept while unknown
    layout.register("extension_ai", ("extension_ai",))
    layout.register("extension_render", ("extension_render",))
    layout.register("extension_new", ("extension_new",))
    assert layout.tray_of("extension_ai") == mine
    assert layout.tray_of("extension_render") is None   # taken out: stays out
    assert layout.tray_of("extension_new") == "extension_new"   # its own
    layout.delete(mine)
    assert layout.trays["extension_ai"] == ["extension_ai"]


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
        assert _keys(win.tray) == ["parts", "entity_info", "components"]
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
        scenes = next(s for s in stack.sections() if s.key == "scenes")
        menu = stack.section_menu(scenes)
        up, down = menu.actions()[:2]
        up.trigger()
        assert _keys(win.tray)[:2] == ["scenes", "entity_info"]
        menu = stack.section_menu(scenes)
        assert not menu.actions()[0].isEnabled()        # already on top
        menu.actions()[1].trigger()
        assert _keys(win.tray)[:2] == ["entity_info", "scenes"]
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


# ---- the Browser and the extensions' panels, dialogs too --------------------

def _extension_dock(win, name="extension_test_panel", title="Test panel"):
    """An extension's panel, registered as ExtensionApp.add_panel does."""
    from PySide6.QtWidgets import QLabel
    dock = QDockWidget(title, win)
    dock.setObjectName(name)
    dock.setWidget(QLabel("hello"))
    dock.setTitleBarWidget(QWidget(dock))
    win._register_extension_dock(dock)
    return dock


def test_the_browser_alone_in_its_tray_shows_bare_and_moves_like_a_section():
    win = _window()
    try:
        manager = win.tray_manager
        browser = win.project_browser
        assert "tray_project_browser" in manager.trays()
        assert browser.widget() is browser.outliner        # as it always was
        mine = manager.new_tray("Mine")
        manager.set_section(mine, "entity_info", True)
        manager.set_section(mine, "browser", True)
        assert _keys(manager.docks[mine]) == ["entity_info", "browser"]
        assert _dock_of(browser.outliner) is manager.docks[mine]
        section = manager.sections["browser"]
        assert section.fill and section._btn.text().strip() == "Browser"
        assert browser.widget() is manager.stacks["tray_project_browser"]
        # With another section in its own tray, it gets its header there.
        manager.set_section("tray_project_browser", "browser", True)
        manager.set_section("tray_project_browser", "layers", True)
        assert _keys(browser) == ["browser", "layers"]
        manager.set_section("tray_properties", "layers", True)
        assert browser.widget() is browser.outliner        # bare again
    finally:
        _close(win)


def test_an_extension_panel_is_a_tray_and_a_dialog():
    from views.manage_trays import ManageTraysDialog
    win = _window()
    try:
        manager = win.tray_manager
        dock = _extension_dock(win)
        panel = dock.widget()
        assert dock.objectName() in manager.trays()
        dialog = ManageTraysDialog(win, manager, select=dock.objectName())
        assert dialog.checks[dock.objectName()].isChecked()
        dialog.deleteLater()
        mine = manager.new_tray("Mine")
        manager.set_section(mine, dock.objectName(), True)
        assert _dock_of(panel) is manager.docks[mine]
        shown = []
        win.set_tray_shown = lambda d, on: shown.append(d)
        win.show_panel_dock(dock)                # ExtensionApp.show_panel
        assert shown == [manager.docks[mine]]
        manager.set_section(mine, dock.objectName(), False)   # in no tray
        win.show_panel_dock(dock)                # brought back home
        assert dock.widget() is panel and shown[-1] is dock
    finally:
        _close(win)


def test_a_tray_made_with_every_tray_closed_joins_their_tabs():
    """It opened a second group of tabs, under the first, once the others
    were shown again."""
    win = _window()
    try:
        for d in win._sidebar_docks():
            win.set_tray_shown(d, False)
        mine = win.tray_manager.new_tray("Mine")
        dock = win.tray_manager.docks[mine]
        win.set_tray_shown(win.tray, True)          # the others come back
        win.set_tray_shown(win.project_browser, True)
        _app.processEvents()
        group = win.tabifiedDockWidgets(dock)
        assert win.tray in group and win.project_browser in group
    finally:
        _close(win)


def test_a_section_header_is_no_taller_than_its_text():
    from views.tray import _Section
    header = _Section("Layers", QWidget(), "layers")._btn
    text = header.fontMetrics().height()
    assert header.sizeHint().height() <= text + 8


def _settle():
    for _ in range(5):
        _app.processEvents()


def _shown_stack(*sections, height=500):
    from views.tray import SectionStack
    stack = SectionStack(list(sections))
    stack.resize(300, height)
    stack.show()
    _settle()
    return stack


def _tall(height=600):
    w = QWidget()
    w.setMinimumHeight(height)
    return w


def test_a_filling_section_takes_the_height_left_until_folded():
    from views.tray import _Section
    small = _Section("Small", _tall(80), "small")
    tree = _Section("Tree", QWidget(), "tree", fill=True)
    stack = _shown_stack(small, tree)
    col = stack._col
    assert small.height() == small.natural_height()
    assert tree.y() + tree.height() >= stack.viewport().height() - 4
    assert (col.stretch(1), col.stretch(2)) == (1, 0)
    tree._btn.setChecked(False)                 # folded: just its header
    _settle()
    assert tree.height() == tree.header_height()
    assert (col.stretch(1), col.stretch(2)) == (0, 1)
    tree._btn.setChecked(True)
    stack.close()


def _drag_grip(section, dy):
    """Press the grip under ``section``, move it by ``dy``, let go."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    grip = section._grip
    at = QPointF(grip.width() / 2, grip.height() / 2)
    start = QPointF(grip.mapToGlobal(at.toPoint()))
    for kind, y, buttons in ((QEvent.MouseButtonPress, 0, Qt.LeftButton),
                             (QEvent.MouseMove, dy, Qt.LeftButton),
                             (QEvent.MouseButtonRelease, dy, Qt.NoButton)):
        _app.sendEvent(grip, QMouseEvent(
            kind, at + QPointF(0, y), start + QPointF(0, y), Qt.LeftButton,
            buttons, Qt.NoModifier))
    _settle()


def test_the_grip_under_a_section_sets_its_height_only_and_pushes_the_rest():
    """The user: the separator changes the section above it, the one
    below is not resized but pushed. And the height is remembered."""
    from views.tray import _Section
    top = _Section("Top", _tall(300), "sep_top")
    below = _Section("Below", _tall(300), "sep_below")
    stack = _shown_stack(top, below)
    before, below_height, below_y = top.height(), below.height(), below.y()
    _drag_grip(top, -120)                                   # dragged up
    assert top.height() == before - 120
    assert below.height() == below_height                   # not resized…
    assert below.y() == below_y - 120                       # …pulled up
    assert top._body.verticalScrollBar().maximum() > 0      # scrolls inside
    _drag_grip(top, 200)                                    # and down
    assert top.height() == before + 80
    assert below.height() == below_height and below.y() == below_y + 80
    kept = top.kept_height()
    assert kept == top.height()
    stack.close()
    again = _shown_stack(_Section("Top", _tall(300), "sep_top"),
                         _Section("Below", _tall(300), "sep_below"))
    first = again.sections()[0]
    assert first.height() == kept                           # the next time
    first._grip.mouseDoubleClickEvent(None)                 # its own again
    _settle()
    assert first.height() == first.natural_height()
    assert first.kept_height() is None
    again.close()


def test_sections_that_do_not_all_fit_stay_whole_and_the_tray_scrolls():
    """Cut to fit, Layers lost its buttons under its own scroll bar."""
    from views.tray import _Section
    short = _Section("Short", _tall(60), "fit_short")
    huge = _Section("Huge", _tall(2000), "fit_huge")
    stack = _shown_stack(short, huge, height=400)
    assert short.height() == short.natural_height()
    assert huge.height() == huge.natural_height()
    assert stack.verticalScrollBar().maximum() > 0
    stack.close()


def test_the_tabs_go_at_the_bottom_from_manage_trays():
    from PySide6.QtWidgets import QTabWidget
    from views.manage_trays import ManageTraysDialog, export_trays
    win = _window()
    try:
        assert win.tabPosition(Qt.RightDockWidgetArea) == QTabWidget.North
        dialog = ManageTraysDialog(win, win.tray_manager)
        assert not dialog.tabs_bottom.isChecked()       # on top, as they come
        dialog.tabs_bottom.setChecked(True)
        assert win.tabPosition(Qt.RightDockWidgetArea) == QTabWidget.South
        assert win.tabPosition(Qt.LeftDockWidgetArea) == QTabWidget.South
        assert export_trays(win)["tabs_bottom"] is True
        dialog.deleteLater()
    finally:
        _close(win)
    win = _window()                                      # remembered
    try:
        assert win.tabPosition(Qt.RightDockWidgetArea) == QTabWidget.South
    finally:
        _close(win)


def test_the_trays_go_to_a_file_and_come_back_from_it():
    import json
    from views.manage_trays import export_trays, import_trays
    win = _window()
    try:
        manager = win.tray_manager
        mine = manager.new_tray("Site")
        manager.set_section(mine, "base_map", True)
        manager.place("parts", "tray_properties", 0)
        win.move_dock(manager.docks[mine], Qt.LeftDockWidgetArea)
        _app.processEvents()
        data = json.loads(json.dumps(export_trays(win)))   # through a file
        assert data["format"] == "ingetrazo-trays"
        assert mine in [t["id"] for t in data["sides"]["left"]["tabs"]]
        # Everything changed back…
        manager.delete(mine)
        manager.place("parts", "tray_properties", 5)
        assert mine not in manager.docks
        # …and the file puts it back: the tray, its section, its side.
        import_trays(win, data)
        _app.processEvents()
        dock = manager.docks[mine]
        assert dock.windowTitle() == "Site" and _keys(dock) == ["base_map"]
        assert win.dockWidgetArea(dock) == Qt.LeftDockWidgetArea
        assert _keys(win.tray)[0] == "parts"
        with pytest.raises(ValueError):
            import_trays(win, {"format": "ingetrazo-shortcuts"})
    finally:
        _close(win)
