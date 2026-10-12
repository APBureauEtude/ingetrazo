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
from core.tray_layout import DEFAULT_SECTIONS, TrayLayout, is_custom
from views import prompts


class TrayManager(QObject):
    """The window's sectioned trays, laid out as :class:`TrayLayout` says.

    ``docks`` are the built-in trays whose body is a views.tray
    SectionStack; their sections are collected once and from then on
    moved between the stacks — the panels themselves never change, so
    ``window.tray.entity_info`` is the same panel wherever it shows."""

    KEY = "ui/tray_layout"

    def __init__(self, window, docks: dict) -> None:
        super().__init__(window)
        self._window = window
        self.docks: dict = dict(docks)
        self.sections: dict = {}
        for tray, dock in self.docks.items():
            for s in dock.widget().sections():
                self.sections[s.key] = s
            self._hook(tray, dock.widget())
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
        """Every sectioned tray id: the built-in ones, then the user's."""
        return [t for t in self.layout.trays if t in self.docks]

    def custom_docks(self) -> list:
        return [self.docks[t] for t in self.layout.custom_trays()
                if t in self.docks]

    def title(self, tray: str) -> str:
        return self.docks[tray].windowTitle()

    def section_title(self, key: str) -> str:
        return self.sections[key].title

    # ---- changing ------------------------------------------------------------
    def apply(self) -> None:
        """Every stack shows the sections the layout gives its tray."""
        placed = set()
        for tray, keys in self.layout.trays.items():
            dock = self.docks.get(tray)
            if dock is None:
                continue
            dock.widget().set_sections(
                [self.sections[k] for k in keys if k in self.sections])
            placed.update(keys)
        for key, section in self.sections.items():
            if key not in placed and section.parentWidget() is not self._parking:
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
        dock = self.docks.pop(tray)
        self.apply()
        self.save()
        self._window.remove_tray_dock(dock)

    def set_section(self, tray: str, key: str, on: bool) -> None:
        self.layout.set_section(tray, key, on)
        self.apply()
        self.save()

    def place(self, key: str, tray: str, index: int) -> None:
        """A section dragged (or moved from its menu) to ``index`` of
        ``tray``."""
        if key not in self.sections or tray not in self.docks:
            return                          # not one of these trays' own
        self.layout.place(key, tray, index)
        self.apply()
        self.save()

    # ---- the docks -----------------------------------------------------------
    def _make_dock(self, tray: str):
        from views.tray import SectionStack
        dock = QDockWidget(self.layout.names[tray], self._window)
        dock.setObjectName(tray)            # where restoreState puts it back
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetMovable
                         | QDockWidget.DockWidgetClosable)
        dock.setWidget(SectionStack())
        dock.setTitleBarWidget(QWidget(dock))   # the tab already names it
        self._hook(tray, dock.widget())
        return dock

    def _hook(self, tray: str, stack) -> None:
        stack.sectionMoved.connect(
            lambda key, index, t=tray: self.place(key, t, index))
        stack.manageRequested.connect(
            lambda t=tray: self._window.open_manage_trays(t))


class ManageTraysDialog(QDialog):
    """Trays on the left, their sections («dialogs») checked in the middle,
    New / Rename / Delete / Close on the right. Every change shows in the
    side bar at once."""

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
        root.addLayout(col, 1)

        col = QVBoxLayout()
        col.addWidget(self._heading(tr("Dialogs:")))
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        checks = QVBoxLayout(box)
        self.checks: dict[str, QCheckBox] = {}
        # Grouped by the tray each comes from, as SketchUp groups them.
        for n, keys in enumerate(DEFAULT_SECTIONS.values()):
            if n:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                checks.addWidget(line)
            for key in keys:
                if key not in manager.sections:
                    continue
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
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        close.setDefault(True)              # Enter closes; it makes nothing
        for b in (self.new_btn, self.rename_btn, self.delete_btn):
            b.setAutoDefault(False)
            col.addWidget(b)
        col.addStretch(1)
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
            elif where != tray:
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
