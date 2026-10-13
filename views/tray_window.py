# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""The side trays' title strip, and the trays out in a window of their own.

Each side of the window that has trays has a title strip over all of them
(:class:`TrayBand`, in a dock of its own, :class:`TrayBandDock`, first on
that side): above the tabs when they are on top, at the top when they are
at the bottom, with the name of the tab in front — SketchUp's trays.
Dragging the strip carries all the trays of that side, every tab, at
once: onto the other side, or out of the main window, where they become a
window of their own (:class:`TrayWindow`) that can go anywhere, a second
screen included.

That window has a title row of its own (:class:`FloatBar`), as SketchUp's
floating trays have: the tab in front, a button that fills the screen the
window is on (and gives its size back), and one that puts the trays back
on their side — drawn as a window with that side filled, not as a close
cross, which read as closing the trays for good. Dragged, the row moves
the window, from screen to screen; its edges resize it. Closing it with
the keyboard puts the trays back too; dragging a tab out of it docks that
one tray. Where the windows were is remembered.

A dialog goes out on its own the same way: its header dragged and let go
where no tray takes it becomes a window of its own (:class:`DialogWindow`)
with the same row — several of them side by side on a second screen,
another dialog dropped into one to keep them together. Its row's button
puts them back in the trays they came from.

The floating tabs of 29-09 were taken back because a tab floating with no
title bar of its own could not be docked again; these windows always have
their row and its button.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QMainWindow,
                               QToolButton, QVBoxLayout, QWidget)

from core.i18n import tr
from views.theme import style as theme_style

#: The strip's look: the bar of a section header.
_BAND_CSS = (
    "TrayBand {{ background: {bar}; border: 1px solid {frame};"
    " border-radius: 3px; }}")
#: A tray window's title row: the same bar, across the window's top.
_BAR_CSS = (
    "FloatBar {{ background: {bar}; border-bottom: 1px solid {frame}; }}")


def band_icon(kind: str, ink: QColor, area=None) -> QIcon:
    """The strips' small icons, in the palette's ink: ``out`` (the trays
    out into a window of their own), ``dock`` (back on the ``area`` side:
    a window with that side filled), ``max`` and ``restore``."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2, 2)                       # drawn on a 16-unit grid
    pen = QPen(ink, 1.3)
    pen.setJoinStyle(Qt.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == "dock":
        p.drawRect(QRectF(1.5, 2.5, 13, 11))
        left = area == Qt.LeftDockWidgetArea
        strip = QRectF(1.5, 2.5, 4.5, 11) if left else QRectF(10, 2.5, 4.5, 11)
        p.fillRect(strip, ink)
        # an arrow towards the filled side
        y, x0, x1 = 8.0, (10.5 if left else 4.0), (7.0 if left else 7.5)
        p.drawLine(QPointF(x0, y), QPointF(x1, y))
        d = -1.6 if left else 1.6
        p.drawLine(QPointF(x1, y), QPointF(x1 - d, y - 1.6))
        p.drawLine(QPointF(x1, y), QPointF(x1 - d, y + 1.6))
    elif kind == "out":
        p.drawRect(QRectF(1.5, 5.5, 9, 9))
        p.drawLine(QPointF(7, 9), QPointF(14, 2))
        p.drawLine(QPointF(14, 2), QPointF(9.5, 2))
        p.drawLine(QPointF(14, 2), QPointF(14, 6.5))
    elif kind == "max":
        p.drawRect(QRectF(2.5, 2.5, 11, 11))
        p.fillRect(QRectF(2.5, 2.5, 11, 2), ink)
    elif kind == "restore":
        p.drawRect(QRectF(2.5, 5.5, 8, 8))
        p.fillRect(QRectF(2.5, 5.5, 8, 1.6), ink)
        p.drawLine(QPointF(5.5, 5.5), QPointF(5.5, 2.5))
        p.drawLine(QPointF(5.5, 2.5), QPointF(13.5, 2.5))
        p.drawLine(QPointF(13.5, 2.5), QPointF(13.5, 10.5))
        p.drawLine(QPointF(13.5, 10.5), QPointF(10.5, 10.5))
    p.end()
    return QIcon(pm)


def _tool_button() -> QToolButton:
    b = QToolButton()
    b.setAutoRaise(True)
    b.setFocusPolicy(Qt.NoFocus)
    return b


class TrayBand(QWidget):
    """The title strip over the trays of one side: the name of the tab in
    front, and a button that takes all the trays of the side out into a
    window of their own. Dragged, it carries them all; double-clicked, it
    is that button; right-clicked, the menu of the tab in front; a tab
    dropped on it joins this side."""

    def __init__(self, main, area) -> None:
        super().__init__()
        self._main = main
        self.area = area
        self._press = None
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 1, 2, 1)
        lay.setSpacing(4)
        self._name = QLabel()
        font = self._name.font()
        font.setBold(True)
        self._name.setFont(font)
        lay.addWidget(self._name, 1)
        self._btn = _tool_button()
        self._btn.setToolTip(tr(
            "Take the trays out into a window of their own"))
        self._btn.clicked.connect(self.toggle)
        lay.addWidget(self._btn)
        self.setAcceptDrops(True)
        self.setStatusTip(tr(
            "Drag to move all the trays of this side, onto the other side "
            "or out of the window; double-click to take them out."))
        theme_style(self, _BAND_CSS)
        self._paint_icons()

    def _paint_icons(self) -> None:
        self._btn.setIcon(band_icon("out", self.palette().buttonText().color()))

    def changeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.type() == QEvent.PaletteChange:
            self._paint_icons()             # the theme's ink
        super().changeEvent(event)

    def name(self) -> str:
        return self._name.text()

    def set_name(self, text: str) -> None:
        self._name.setText(text)

    def toggle(self) -> None:
        self._main.detach_side(self.area)

    # ---- the mouse: taken here, or Qt drags one tab, not the side ----------
    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.button() == Qt.LeftButton:
            self._press = event.position().toPoint()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt override
        from PySide6.QtWidgets import QApplication
        press = self._press
        if (press is not None and event.buttons() & Qt.LeftButton
                and (event.position().toPoint() - press).manhattanLength()
                >= QApplication.startDragDistance()):
            self._press = None
            self._main.drag_band(self, press)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._press = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._press = None
        self.toggle()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._main.band_menu(self._main.front_tray(self.area)).exec(
            event.globalPos())
        event.accept()

    # ---- a tab dropped on it joins this side -------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.mimeData().hasFormat(self._main.DOCK_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.mimeData().hasFormat(self._main.DOCK_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.mimeData().hasFormat(self._main.DOCK_MIME):
            self._main.drop_on_side(event.mimeData(), self.area)
            event.acceptProposedAction()


class TrayBandDock(QDockWidget):
    """Where a side's :class:`TrayBand` lives: a dock of its own, first on
    that side, one strip tall — so the strip stands over the tab bar, not
    inside one tray. It cannot be moved or closed; it shows while its side
    has trays open."""

    def __init__(self, main, area) -> None:
        super().__init__(main)
        self.setObjectName("tray_band_left" if area == Qt.LeftDockWidgetArea
                           else "tray_band_right")
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setAllowedAreas(area)
        self.setTitleBarWidget(QWidget(self))
        self.band = TrayBand(main, area)
        self.setWidget(self.band)
        self.setFixedHeight(self.band.sizeHint().height())


class FloatBar(QWidget):
    """The title row of a window of trays or dialogs: its name; a button
    that fills the screen the window is on, or gives its size back; and
    one that puts what it holds back (``on_back``), drawn as a window with
    its ``area`` side filled. Dragged, it moves the window (the system's
    move: across screens, to an edge); double-clicked, it fills the screen
    or gives the size back; right-clicked, ``menu()``'s menu."""

    def __init__(self, window, on_back, back_tip: str,
                 area=Qt.RightDockWidgetArea, menu=None) -> None:
        super().__init__(window)
        self._win = window
        self._area = area
        self._menu = menu
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 3, 2)
        lay.setSpacing(2)
        self._name = QLabel()
        font = self._name.font()
        font.setBold(True)
        self._name.setFont(font)
        lay.addWidget(self._name, 1)
        self.max_btn = _tool_button()
        self.max_btn.clicked.connect(window.toggle_max)
        lay.addWidget(self.max_btn)
        self.dock_btn = _tool_button()
        self.dock_btn.setToolTip(back_tip)
        self.dock_btn.clicked.connect(lambda _c=False: on_back())
        lay.addWidget(self.dock_btn)
        self.setStatusTip(tr(
            "Drag to move the window; double-click to fill the screen or "
            "give it its size back."))
        theme_style(self, _BAR_CSS)
        self.refresh()

    def name(self) -> str:
        return self._name.text()

    def set_name(self, text: str) -> None:
        self._name.setText(text)

    def refresh(self) -> None:
        ink = self.palette().buttonText().color()
        full = self._win.is_max()
        self.max_btn.setIcon(band_icon("restore" if full else "max", ink))
        self.max_btn.setToolTip(
            tr("Give the window its size back") if full
            else tr("Fill the screen the window is on"))
        self.dock_btn.setIcon(band_icon("dock", ink, self._area))

    def changeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.type() == QEvent.PaletteChange:
            self.refresh()                  # the theme's ink
        super().changeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.button() == Qt.LeftButton and not self._win.is_max():
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._win.toggle_max()
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 — Qt override
        menu = self._menu() if self._menu is not None else None
        if menu is not None:
            menu.exec(event.globalPos())
        event.accept()


class _Frameless:
    """What a window with no system frame needs (mixed into a QWidget
    subclass): edges that resize it, a line around it, and filling the
    work area of its screen and back — a frameless window that Windows
    maximised would cover the task bar. Calls ``_max_changed()``."""

    #: The edge that resizes the window, in pixels.
    BORDER = 5

    _CURSORS = (
        ((Qt.LeftEdge | Qt.TopEdge), Qt.SizeFDiagCursor),
        ((Qt.RightEdge | Qt.BottomEdge), Qt.SizeFDiagCursor),
        ((Qt.RightEdge | Qt.TopEdge), Qt.SizeBDiagCursor),
        ((Qt.LeftEdge | Qt.BottomEdge), Qt.SizeBDiagCursor),
    )

    def _init_frameless(self) -> None:
        self._normal: QRect | None = None   # its size before filling a screen
        self.setMouseTracking(True)

    def _max_changed(self) -> None:
        pass

    # ---- filling a screen --------------------------------------------------------
    def is_max(self) -> bool:
        return getattr(self, "_normal", None) is not None

    def normal_rect(self) -> QRect:
        """Its size and place when it does not fill a screen."""
        return QRect(self._normal) if self._normal is not None \
            else self.geometry()

    def toggle_max(self) -> None:
        """Fill the work area of the screen it is on, or go back to the
        size and place it had."""
        if self._normal is None:
            self._normal = self.geometry()
            screen = self.screen()
            if screen is not None:
                self.setGeometry(screen.availableGeometry())
        else:
            normal, self._normal = self._normal, None
            self.setGeometry(normal)
        self._max_changed()

    def place(self, entry: dict | None, fallback: QPoint | None = None) -> None:
        """Where ``entry`` says (``rect``, ``maximized``) — on a screen that
        is still there, or by ``fallback``'s — filling it if it did."""
        from PySide6.QtGui import QGuiApplication
        rect = (entry or {}).get("rect")
        if isinstance(rect, list) and len(rect) == 4 \
                and all(isinstance(v, int) for v in rect):
            r = QRect(*rect)
            if QGuiApplication.screenAt(r.center()) is None:
                screen = QGuiApplication.screenAt(fallback) \
                    if fallback is not None else None
                screen = screen or QGuiApplication.primaryScreen()
                if screen is not None:
                    r.moveCenter(screen.availableGeometry().center())
            self.setGeometry(r)
        if (entry or {}).get("maximized") is True and not self.is_max():
            self.toggle_max()

    def frame_entry(self) -> dict:
        r = self.normal_rect()
        return {"rect": [r.x(), r.y(), r.width(), r.height()],
                "maximized": self.is_max()}

    # ---- the edges resize it -----------------------------------------------------
    def _edges_at(self, pos: QPoint):
        if self.is_max():
            return Qt.Edge(0)
        b, r = self.BORDER, self.rect()
        edges = Qt.Edge(0)
        if pos.x() < b:
            edges |= Qt.LeftEdge
        elif pos.x() >= r.width() - b:
            edges |= Qt.RightEdge
        if pos.y() < b:
            edges |= Qt.TopEdge
        elif pos.y() >= r.height() - b:
            edges |= Qt.BottomEdge
        return edges

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt override
        edges = self._edges_at(event.position().toPoint())
        cursor = next((c for e, c in self._CURSORS if edges == e), None)
        if cursor is None and edges & (Qt.LeftEdge | Qt.RightEdge):
            cursor = Qt.SizeHorCursor
        elif cursor is None and edges & (Qt.TopEdge | Qt.BottomEdge):
            cursor = Qt.SizeVerCursor
        if cursor is None:
            self.unsetCursor()
        else:
            self.setCursor(cursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        edges = self._edges_at(event.position().toPoint())
        if event.button() == Qt.LeftButton and edges != Qt.Edge(0):
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemResize(edges)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt override
        """No system frame: a line of its own around it."""
        from views.theme import tokens
        p = QPainter(self)
        p.setPen(QColor(tokens()["frame"]))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class TrayWindow(_Frameless, QMainWindow):
    """The trays of one side out of the main window: a window of the main
    one (it stays above it, and can go to another screen) with no system
    frame — its :class:`FloatBar` is its title row, and its edges resize
    it. Closing it (Alt+F4) puts the trays back on their side."""

    def __init__(self, main, area) -> None:
        super().__init__(main, Qt.Window | Qt.FramelessWindowHint)
        self._init_frameless()
        self._main = main
        self.area = area
        self._closing = False
        self.setObjectName("tray_window_left" if area == Qt.LeftDockWidgetArea
                           else "tray_window_right")
        # The docks fill it: a placeholder in the middle, hidden.
        centre = QWidget()
        centre.hide()
        self.setCentralWidget(centre)
        self.setDockOptions(QMainWindow.AnimatedDocks
                            | QMainWindow.AllowTabbedDocks)
        self.setTabPosition(Qt.AllDockWidgetAreas,
                            main.tabPosition(Qt.RightDockWidgetArea))
        self.setWindowTitle(tr("Trays"))
        tip = (tr("Put the trays back on the left side of the main window")
               if area == Qt.LeftDockWidgetArea else
               tr("Put the trays back on the right side of the main window"))
        self.bar = FloatBar(self, lambda: main.dock_back(self), tip, area,
                            lambda: main.band_menu(self.front()))
        self.setMenuWidget(self.bar)
        b = self.BORDER
        self.setContentsMargins(b, b, b, b)

    def _max_changed(self) -> None:
        self.bar.refresh()
        self._main.remember_tray_windows()

    def docks(self) -> list:
        return [d for d in self.findChildren(QDockWidget)
                if d.parentWidget() is self]

    def take(self, docks, front=None) -> None:
        """``docks`` in here, tabbed in this order; ``front`` in front."""
        from PySide6.QtCore import QTimer
        here = self.docks()
        for d in docks:
            self.addDockWidget(Qt.RightDockWidgetArea, d)
            if here:
                self.tabifyDockWidget(here[0], d)
            else:
                here = [d]
            d.visibilityChanged.connect(self._follow_front)
        if front is not None and not front.isHidden():
            front.raise_()
        QTimer.singleShot(0, self, self._follow_front)

    def front(self):
        return next((d for d in self.docks() if d.isVisible()
                     and not d.visibleRegion().isEmpty()), None)

    def _follow_front(self, *_a) -> None:
        """The row's name and the window's title are the tab in front."""
        d = self.front()
        if d is not None:
            self.setWindowTitle(d.windowTitle())
            self.bar.set_name(d.windowTitle())

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if not self._closing:
            self._main.dock_back(self)
        event.accept()

    def moveEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().moveEvent(event)
        self._main.remember_tray_windows()

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self._main.remember_tray_windows()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Right-click on its tabs: the tray menu, for the tab there."""
        from PySide6.QtWidgets import QTabBar
        child = self.childAt(event.pos())
        while child is not None and not isinstance(child, QTabBar):
            child = child.parentWidget()
        if child is None:
            super().contextMenuEvent(event)
            return
        dock = self._main._dock_of_tab(
            child, child.tabAt(child.mapFrom(self, event.pos())))
        self._main.band_menu(dock or self.front()).exec(event.globalPos())
        event.accept()


class DialogWindow(_Frameless, QWidget):
    """Dialogs out of their trays, in a window of their own (a window of
    the main one, with no system frame): its :class:`FloatBar` names them
    and puts them back in the trays they came from; under it, a
    views.tray SectionStack — their headers fold them, drag them back into
    a tray or bring another dialog in, and the grips size them. Its tray in
    the layout is ``tray`` (core.tray_layout's ``tray_float_…``). Closing
    it (Alt+F4) puts the dialogs back."""

    def __init__(self, main, manager, tray: str) -> None:
        super().__init__(main, Qt.Window | Qt.FramelessWindowHint)
        self._init_frameless()
        self._manager = manager
        self.tray = tray
        self._closing = False
        self.setObjectName(tray)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        b = self.BORDER
        lay.setContentsMargins(b, b, b, b)
        lay.setSpacing(0)
        self.bar = FloatBar(
            self, lambda: manager.put_back(tray),
            tr("Put the dialogs back in the trays they came from"))
        from views.tray import SectionStack
        self.stack = SectionStack()
        lay.addWidget(self.bar)
        lay.addWidget(self.stack, 1)
        self.setWindowTitle(tr("Dialogs"))

    def follow(self) -> None:
        """Its row and title name the dialogs it holds."""
        names = " · ".join(s.title for s in self.stack.sections())
        self.bar.set_name(names)
        self.setWindowTitle(names or tr("Dialogs"))

    def stack_offset(self) -> QPoint:
        """Where its first dialog's header is, from its top-left corner."""
        b = self.BORDER
        return QPoint(b, b + self.bar.sizeHint().height())

    def _max_changed(self) -> None:
        self.bar.refresh()
        self._manager.remember_windows()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if not self._closing:
            self._manager.put_back(self.tray)
        event.accept()

    def moveEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().moveEvent(event)
        self._manager.remember_windows()

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self._manager.remember_windows()


def tab_order(win, docks: list) -> list:
    """``docks`` of the main window ``win`` (the app's or a tray window) in
    the order their tabs show, then the ones without a tab on screen."""
    from PySide6.QtWidgets import QTabBar
    ordered = []
    for bar in win.findChildren(QTabBar):
        # Qt keeps spare tab bars around, out of sight.
        if bar.parent() is not win or not bar.isVisible() \
                or not win.rect().contains(bar.mapTo(win, QPoint(0, 0))):
            continue
        for i in range(bar.count()):
            text = bar.tabText(i)
            d = next((x for x in docks
                      if x.windowTitle() == text and x not in ordered), None)
            if d is not None:
                ordered.append(d)
    return ordered + [d for d in docks if d not in ordered]
