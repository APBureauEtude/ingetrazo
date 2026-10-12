# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Window ▸ Manage Trays: trays of your own, and which sections each shows.

SketchUp's Manage Trays dialog: the trays on the left, the sections it
calls *dialogs* in the middle — checked when the selected tray shows them
— and New / Rename / Delete / Close. A tray of your own is one more tab of
the side bar; a section is in one tray at a time, so checking it in one
tray takes it out of the other, and a section left in no tray waits,
hidden, until it is checked again. Deleting a tray gives its sections
back to the trays they came from.

Every tab is a tray and every panel a dialog: the Browser and each
extension's panel too. Such a panel alone in its own tray shows bare, as
it always did — no header under a tab that already names it, and
``dock.widget()`` still the panel; put with others, or in another tray,
it gets a header like any section, and fills the height left.

Export… / Import… write and read the whole arrangement — the trays, their
sections, which side each tab is on, in what order, which are open, the
tabs on top or at the bottom — as a JSON file, as the keyboard shortcuts
are.

:class:`TrayManager` keeps the window's trays in step with the layout
(core.tray_layout) and saves it; :class:`ManageTraysDialog` is the dialog.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDockWidget, QFrame,
                               QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from core.i18n import tr
from core.tray_layout import TrayLayout, is_custom
from views import prompts

#: What an exported trays file says it is.
EXPORT_FORMAT = "ingetrazo-trays"


class TrayManager(QObject):
    """The window's trays, laid out as :class:`TrayLayout` says.

    ``docks`` are the built-in trays whose body is a views.tray
    SectionStack; their sections are collected once and from then on
    moved between the stacks — the panels themselves never change, so
    ``window.tray.entity_info`` is the same panel wherever it shows.
    ``panels`` are the panels that are a tray's whole body (the Browser;
    each extension's, :meth:`adopt`-ed when it loads), keyed by their
    section id."""

    KEY = "ui/tray_layout"

    def __init__(self, window, docks: dict, panels: dict | None = None) -> None:
        super().__init__(window)
        self._window = window
        self.docks: dict = dict(docks)
        self.stacks: dict = {}
        self.sections: dict = {}
        self.titles: dict = {}
        #: A panel shown bare in its own tray: section id → the panel.
        self.panels: dict = {}
        #: Its tray → its section id.
        self._own: dict = {}
        for tray, dock in self.docks.items():
            self.stacks[tray] = dock.widget()
            for s in dock.widget().sections():
                self.sections[s.key] = s
                self.titles[s.key] = s.title
            self._hook(tray, dock.widget())
        for key, dock in (panels or {}).items():
            self._take_panel(dock, key)
        # A section in no tray waits here, hidden: its panel lives on
        # (the window still refreshes it) but is never on screen.
        self._parking = QWidget(window)
        self._parking.hide()
        from PySide6.QtCore import QSettings      # looked up when used
        self.layout = TrayLayout.from_json(QSettings().value(self.KEY))
        for tray in self.layout.custom_trays():
            self.docks[tray] = self._make_dock(tray)
        self.apply()

    # ---- reading -------------------------------------------------------------
    def trays(self) -> list[str]:
        """Every tray with a tab: the window's own and the extensions',
        then the user's."""
        mine = [t for t in self.layout.trays if t in self.docks]
        return ([t for t in mine if not is_custom(t)]
                + [t for t in mine if is_custom(t)])

    def groups(self) -> list[list[str]]:
        """The sections, grouped by the tray they come from (the order of
        Manage Trays' check boxes)."""
        groups = []
        for home, keys in self.layout.homes.items():
            mine = [k for k in keys if k in self.titles]
            if mine:
                groups.append(mine)
        return groups

    def custom_docks(self) -> list:
        return [self.docks[t] for t in self.layout.custom_trays()
                if t in self.docks]

    def title(self, tray: str) -> str:
        return self.docks[tray].windowTitle()

    def section_title(self, key: str) -> str:
        return self.titles[key]

    def dock_showing(self, key: str):
        """The tray a section is on screen in, or ``None``."""
        w = self.panels.get(key) or self.sections.get(key)
        while w is not None and not isinstance(w, QDockWidget):
            w = w.parentWidget()
        return w

    # ---- an extension's panel ------------------------------------------------
    def adopt(self, dock) -> None:
        """An extension's panel: its tab is a tray, and the panel a dialog
        that can go in any tray — where the saved layout put it."""
        tray = dock.objectName()
        if tray in self.docks or dock.widget() is None:
            return
        self._take_panel(dock, tray)
        self.layout.register(tray, (tray,))
        self.apply()
        self.save()

    def _take_panel(self, dock, key: str) -> None:
        tray = dock.objectName()
        self.docks[tray] = dock
        self.panels[key] = dock.widget()
        self.titles[key] = dock.windowTitle()
        self._own[tray] = key

    def show_dialog(self, key: str) -> bool:
        """Bring the tray showing ``key`` forward — back in its own tray
        first if it was in none. False when ``key`` is not a dialog."""
        if key not in self.titles:
            return False
        if self.layout.tray_of(key) is None:
            self.set_section(self.layout.home_of(key), key, True)
        dock = self.dock_showing(key)
        if dock is None:
            return False
        self._window.set_tray_shown(dock, True)
        return True

    # ---- changing ------------------------------------------------------------
    def apply(self) -> None:
        """Every tray shows the sections the layout gives it."""
        shown = {t: [k for k in keys if k in self.titles]
                 for t, keys in self.layout.trays.items() if t in self.docks}
        # A section in a tray that has no tab this time (an extension not
        # loaded) shows in its own tray meanwhile; the layout keeps it there.
        for key in self.titles:
            tray = self.layout.tray_of(key)
            home = self.layout.home_of(key)
            if tray is not None and tray not in self.docks and home in shown:
                shown[home].append(key)
        in_stacks = set()
        for tray, keys in shown.items():
            dock = self.docks[tray]
            own = self._own.get(tray)
            if own is not None and keys == [own]:
                # Alone in its own tray: the panel itself, as it always was.
                if tray in self.stacks:
                    self.stacks[tray].set_sections([])
                self._set_body(dock, self.panels[own])
                continue
            sections = [self._section(k) for k in keys]
            stack = self._stack(tray)
            stack.set_sections(sections)
            in_stacks.update(sections)
            self._set_body(dock, stack)
        for key in self.titles:
            placed = any(key in keys for keys in shown.values())
            if not placed:
                self._section(key)          # a bare panel, wrapped to wait
        for section in self.sections.values():
            if section not in in_stacks \
                    and section.parentWidget() is not self._parking:
                section.setParent(self._parking)

    def save(self) -> None:
        from PySide6.QtCore import QSettings
        QSettings().setValue(self.KEY, self.layout.to_json())

    def new_tray(self, name: str) -> str:
        """A new, empty tray called ``name``: a new tab, in front."""
        tray = self.layout.new_tray(name)
        dock = self.docks[tray] = self._make_dock(tray)
        self.save()
        self._window.add_tray_dock(dock)
        return tray

    def rename(self, tray: str, name: str) -> None:
        self.layout.rename(tray, name)
        self.docks[tray].setWindowTitle(name)
        self.save()

    def delete(self, tray: str) -> None:
        """Remove one of the user's trays; its sections go home."""
        self.layout.delete(tray)
        self._drop_dock(tray)
        self.apply()
        self.save()

    def set_section(self, tray: str, key: str, on: bool) -> None:
        self.layout.set_section(tray, key, on)
        self.apply()
        self.save()

    def place(self, key: str, tray: str, index: int) -> None:
        """A section dragged (or moved from its menu) to ``index`` of
        ``tray``."""
        if key not in self.titles or tray not in self.docks:
            return                          # not one of these trays' own
        self.layout.place(key, tray, index)
        self.apply()
        self.save()

    def load(self, layout: TrayLayout) -> None:
        """Another arrangement (an imported file): the user's trays it does
        not have go, the ones it has are made or renamed."""
        for tray, keys in self.layout.homes.items():
            if tray not in layout.homes:
                layout.register(tray, keys)     # the extensions loaded now
        for tray in self.layout.custom_trays():
            if tray not in layout.trays:
                self._drop_dock(tray)
        self.layout = layout
        for tray in layout.custom_trays():
            if tray in self.docks:
                self.docks[tray].setWindowTitle(layout.names[tray])
            else:
                dock = self.docks[tray] = self._make_dock(tray)
                self._window.add_tray_dock(dock)
        self.apply()
        self.save()

    # ---- the docks -----------------------------------------------------------
    def _section(self, key: str):
        """The section showing ``key``; a bare panel is wrapped in one."""
        section = self.sections.get(key)
        panel = self.panels.get(key)
        if section is None:
            from views.tray import _Section
            section = _Section(self.titles[key], panel, key, fill=True,
                               fold_key=f"tray/collapsed/{key}")
            self.sections[key] = section
        if panel is not None:
            section.take_back_content()
        return section

    def _stack(self, tray: str):
        stack = self.stacks.get(tray)
        if stack is None:
            from views.tray import SectionStack
            stack = self.stacks[tray] = SectionStack()
            self._hook(tray, stack)
        return stack

    def _set_body(self, dock, widget) -> None:
        old = dock.widget()
        if old is widget:
            return
        dock.setWidget(widget)
        widget.show()
        if old is not None and old in self.stacks.values():
            old.setParent(self._parking)    # kept for when it is needed

    def _make_dock(self, tray: str):
        from views.tray import SectionStack
        dock = QDockWidget(self.layout.names[tray], self._window)
        dock.setObjectName(tray)            # where restoreState puts it back
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetMovable
                         | QDockWidget.DockWidgetClosable)
        stack = self.stacks[tray] = SectionStack()
        dock.setWidget(stack)
        dock.setTitleBarWidget(QWidget(dock))   # the tab already names it
        self._hook(tray, stack)
        return dock

    def _drop_dock(self, tray: str) -> None:
        dock = self.docks.pop(tray)
        stack = self.stacks.pop(tray, None)
        if stack is not None:
            for s in stack.sections():
                s.setParent(self._parking)  # out before the dock goes
        self._window.remove_tray_dock(dock)

    def _hook(self, tray: str, stack) -> None:
        stack.sectionMoved.connect(
            lambda key, index, t=tray: self.place(key, t, index))
        stack.manageRequested.connect(
            lambda t=tray: self._window.open_manage_trays(t))


# ---- Export… / Import… ---------------------------------------------------------

_SIDES = (("right", Qt.RightDockWidgetArea), ("left", Qt.LeftDockWidgetArea))


def _tab_order(window, docks: list) -> list:
    """``docks`` in the order their tabs show, then the closed ones."""
    from PySide6.QtCore import QPoint
    ordered = []
    for bar in window._dock_tab_bars():
        # Qt keeps spare tab bars around, out of sight.
        if not bar.isVisible() or not window.rect().contains(
                bar.mapTo(window, QPoint(0, 0))):
            continue
        for i in range(bar.count()):
            d = window._dock_of_tab(bar, i)
            if d in docks and d not in ordered:
                ordered.append(d)
    return ordered + [d for d in docks if d not in ordered]


def export_trays(window) -> dict:
    """The trays as a file: their sections (the layout), and for each side
    of the window its tabs in order, which are open, the one in front and
    the side's width."""
    sides = {}
    for name, area in _SIDES:
        docks = [d for d in window._sidebar_docks()
                 if window.dockWidgetArea(d) == area]
        front = next((d for d in docks if d.isVisible()
                      and not d.visibleRegion().isEmpty()), None)
        sides[name] = {
            "tabs": [{"id": d.objectName(), "shown": not d.isHidden()}
                     for d in _tab_order(window, docks)],
            "front": front.objectName() if front is not None else None,
            "width": front.width() if front is not None else None,
        }
    return {"format": EXPORT_FORMAT, "version": 1,
            "layout": window.tray_manager.layout.to_dict(), "sides": sides,
            "tabs_bottom": window.tray_tabs_bottom()}


def import_trays(window, data) -> None:
    """Put the window's trays as a file from :func:`export_trays` has
    them. Tabs the file names that this window does not have (an
    extension not installed) are left out, and tabs it does not name stay
    where they are. ValueError for a file that is not a trays file."""
    if (not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT
            or not isinstance(data.get("layout"), dict)):
        raise ValueError(tr("This is not an IngeTrazo trays file."))
    window.tray_manager.load(TrayLayout.from_dict(data["layout"]))
    if isinstance(data.get("tabs_bottom"), bool):
        window.set_tray_tabs_bottom(data["tabs_bottom"])
    by_id = {d.objectName(): d for d in window._sidebar_docks()}
    sides = data.get("sides") if isinstance(data.get("sides"), dict) else {}
    for name, area in _SIDES:
        side = sides.get(name) if isinstance(sides.get(name), dict) else {}
        tabs = [t for t in side.get("tabs") or ()
                if isinstance(t, dict) and t.get("id") in by_id]
        docks = [by_id[t["id"]] for t in tabs]
        for d in docks:
            window.addDockWidget(area, d)
        for first, nxt in zip(docks, docks[1:]):
            window.tabifyDockWidget(first, nxt)
        for t, d in zip(tabs, docks):
            window.set_tray_shown(d, bool(t.get("shown", True)))
        front = by_id.get(side.get("front"))
        if front in docks and not front.isHidden():
            front.raise_()
            width = side.get("width")
            if isinstance(width, int) and width > 0:
                window.resizeDocks([front], [width], Qt.Horizontal)
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, window, window._style_dock_tabs)
    QTimer.singleShot(0, window, window._place_sidebar_handle)


class ManageTraysDialog(QDialog):
    """Trays on the left, their sections («dialogs») checked in the middle,
    New / Rename / Delete, Export… / Import… and Close on the right. Every
    change shows in the side bar at once."""

    def __init__(self, window, manager: TrayManager, select: str | None = None):
        super().__init__(window)
        self.setWindowTitle(tr("Manage Trays"))
        self._window = window
        self._manager = manager
        root = QHBoxLayout(self)

        col = QVBoxLayout()
        col.addWidget(self._heading(tr("Trays:")))
        self.tray_list = QListWidget()
        self.tray_list.setMinimumWidth(170)
        col.addWidget(self.tray_list, 1)
        self.tabs_bottom = QCheckBox(tr("Tabs at the bottom"))
        self.tabs_bottom.setToolTip(tr(
            "Put the trays' tabs under them instead of on top."))
        self.tabs_bottom.setChecked(window.tray_tabs_bottom())
        self.tabs_bottom.toggled.connect(window.set_tray_tabs_bottom)
        col.addWidget(self.tabs_bottom)
        root.addLayout(col, 1)

        col = QVBoxLayout()
        col.addWidget(self._heading(tr("Dialogs:")))
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        checks = QVBoxLayout(box)
        self.checks: dict[str, QCheckBox] = {}
        # Grouped by the tray each comes from, as SketchUp groups them.
        for n, keys in enumerate(manager.groups()):
            if n:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                checks.addWidget(line)
            for key in keys:
                check = QCheckBox(manager.section_title(key))
                check.toggled.connect(
                    lambda on, k=key: self._on_check(k, on))
                checks.addWidget(check)
                self.checks[key] = check
        checks.addStretch(1)
        col.addWidget(box, 1)
        root.addLayout(col, 1)

        col = QVBoxLayout()
        self.new_btn = QPushButton(tr("New"))
        self.new_btn.setToolTip(tr("Make a tray of your own: a new tab of "
                                   "the side bar."))
        self.new_btn.clicked.connect(self._on_new)
        self.rename_btn = QPushButton(tr("Rename"))
        self.rename_btn.clicked.connect(self._on_rename)
        self.delete_btn = QPushButton(tr("Delete"))
        self.delete_btn.setToolTip(tr(
            "Delete this tray; its sections go back to the trays they "
            "came from."))
        self.delete_btn.clicked.connect(self._on_delete)
        export = QPushButton(tr("Export…"))
        export.setToolTip(tr(
            "Save the trays — their sections, side, order and which are "
            "open — to a file, to take them to another computer"))
        export.clicked.connect(self._on_export)
        imp = QPushButton(tr("Import…"))
        imp.setToolTip(tr("Arrange the trays as a file saved them"))
        imp.clicked.connect(self._on_import)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        close.setDefault(True)              # Enter closes; it makes nothing
        for b in (self.new_btn, self.rename_btn, self.delete_btn):
            b.setAutoDefault(False)
            col.addWidget(b)
        col.addStretch(1)
        for b in (export, imp):
            b.setAutoDefault(False)
            col.addWidget(b)
        col.addSpacing(12)
        col.addWidget(close)
        root.addLayout(col)

        self.tray_list.currentRowChanged.connect(lambda _r: self._sync())
        self._fill(select)

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    # ---- the list and the check boxes --------------------------------------
    def current_tray(self) -> str | None:
        item = self.tray_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _fill(self, select: str | None = None) -> None:
        self.tray_list.blockSignals(True)
        self.tray_list.clear()
        for tray in self._manager.trays():
            item = QListWidgetItem(self._manager.title(tray))
            item.setData(Qt.UserRole, tray)
            self.tray_list.addItem(item)
            if tray == select:
                self.tray_list.setCurrentItem(item)
        if self.tray_list.currentItem() is None and self.tray_list.count():
            self.tray_list.setCurrentRow(0)
        self.tray_list.blockSignals(False)
        self._sync()

    def _sync(self) -> None:
        tray = self.current_tray()
        layout = self._manager.layout
        for key, check in self.checks.items():
            where = layout.tray_of(key)
            check.blockSignals(True)
            check.setEnabled(tray is not None)
            check.setChecked(tray is not None and where == tray)
            check.blockSignals(False)
            if where is None:
                check.setToolTip(tr("In no tray: check it to show it in "
                                    "this one."))
            elif where != tray and where in self._manager.docks:
                check.setToolTip(tr("Now in the tray “{tray}”: checking it "
                                    "moves it here.",
                                    tray=self._manager.title(where)))
            else:
                check.setToolTip("")
        own = tray is not None and is_custom(tray)
        self.rename_btn.setEnabled(own)
        self.delete_btn.setEnabled(own)

    def _on_check(self, key: str, on: bool) -> None:
        tray = self.current_tray()
        if tray is not None:
            self._manager.set_section(tray, key, on)
        self._sync()

    # ---- New / Rename / Delete -----------------------------------------------
    def _name_taken(self, name: str, but: str | None = None) -> bool:
        """Whether a side-bar tab already has this name — the tabs are
        told apart by their text."""
        wanted = name.strip().casefold()
        return any(d.windowTitle().strip().casefold() == wanted
                   for d in self._window._sidebar_docks()
                   if d.objectName() != but)

    def _ask_name(self, title: str, text: str, but: str | None = None):
        """A name from the user, or ``None``: empty, cancelled or taken."""
        name, ok = prompts.get_text(self, title, tr("Name:"), text=text)
        name = name.strip()
        if not ok or not name:
            return None
        if self._name_taken(name, but):
            QMessageBox.warning(self, tr("Manage Trays"), tr(
                "There is already a tray called “{name}”.", name=name))
            return None
        return name

    def _free_name(self) -> str:
        n = 1
        while self._name_taken(tr("Tray {n}", n=n)):
            n += 1
        return tr("Tray {n}", n=n)

    def _on_new(self) -> None:
        name = self._ask_name(tr("New Tray"), self._free_name())
        if name is not None:
            self.new_tray(name)

    def new_tray(self, name: str) -> str:
        tray = self._manager.new_tray(name)
        self._fill(tray)
        return tray

    def _on_rename(self) -> None:
        tray = self.current_tray()
        if tray is None or not is_custom(tray):
            return
        name = self._ask_name(tr("Rename Tray"), self._manager.title(tray),
                              but=tray)
        if name is not None:
            self._manager.rename(tray, name)
            self._fill(tray)

    def _on_delete(self) -> None:
        tray = self.current_tray()
        if tray is None or not is_custom(tray):
            return
        answer = QMessageBox.question(
            self, tr("Delete Tray"),
            tr("Delete the tray “{name}”? Its sections go back to the trays "
               "they came from.", name=self._manager.title(tray)))
        if answer == QMessageBox.Yes:
            self._manager.delete(tray)
            self._fill()

    # ---- Export… / Import… -----------------------------------------------------
    def _on_export(self) -> None:
        import json
        from views.filedialogs import file_dialogs
        path, _ = file_dialogs.getSaveFileName(
            self, tr("Export trays"), "ingetrazo-trays.json",
            tr("Trays (*.json)"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_trays(self._window), f, indent=1,
                          ensure_ascii=False)
        except OSError as exc:
            QMessageBox.warning(self, tr("Export trays"), str(exc))

    def _on_import(self) -> None:
        import json
        from views.filedialogs import file_dialogs
        path, _ = file_dialogs.getOpenFileName(
            self, tr("Import trays"), "", tr("Trays (*.json)"))
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                import_trays(self._window, json.load(f))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr("Import trays"), str(exc))
            return
        self.tabs_bottom.blockSignals(True)
        self.tabs_bottom.setChecked(self._window.tray_tabs_bottom())
        self.tabs_bottom.blockSignals(False)
        self._fill(self.current_tray())
