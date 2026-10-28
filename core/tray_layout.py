# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Which sections each side tray holds, and in what order — the data behind
Window ▸ Manage Trays.

SketchUp's words: a *tray* is a tab of the side bar, a *dialog* is one of
the folding sections inside it (Entity info, Layers, Materials…, the
Browser, an extension's panel). The built-in trays start with their
factory sections; the user can make trays of their own, put any section in
any tray (a section is in one tray at a time), take one out of every tray,
and reorder the sections of a tray.

An extension's panel is a tray of its own with one section; it is
:meth:`TrayLayout.register`-ed when the extension loads, after the saved
layout was read — so what the layout says of trays and sections it does
not know yet is kept, and used when they turn up.

Plain data, no Qt: saved as JSON in the settings (``ui/tray_layout``).
Section and tray ids are stable names, never shown — the titles are the
translated ones the window gives them.
"""
from __future__ import annotations

import json
import uuid

#: The factory trays and their sections, in order. A tray id is its
#: dock's ``objectName`` (which the saved window layout is keyed by).
DEFAULT_SECTIONS: dict[str, tuple[str, ...]] = {
    "tray_properties": ("entity_info", "scenes", "materials",
                        "components", "parts"),
    "tray_project_browser": ("browser",),
    "tray_layers": ("layers",),
    "tray_bim": ("bim",),
    "tray_georef": ("base_map", "survey"),
}

#: Every tray the user makes is named ``tray_user_<hex>``: never reused, so
#: a deleted tray's saved place or hidden state can't land on a new one.
CUSTOM_PREFIX = "tray_user_"

#: A dialog out in a window of its own is in a tray of its own, with no
#: tab: ``tray_float_<hex>``, the window.
FLOAT_PREFIX = "tray_float_"


def all_sections() -> list[str]:
    """Every built-in section id, in the factory order."""
    return [s for sections in DEFAULT_SECTIONS.values() for s in sections]


def is_custom(tray: str) -> bool:
    return tray.startswith(CUSTOM_PREFIX)


def is_float(tray) -> bool:
    return isinstance(tray, str) and tray.startswith(FLOAT_PREFIX)


class TrayLayout:
    """Tray id → its section ids in order, plus the user's trays' names.

    ``homes`` are the trays sections come from: the built-in ones, and
    those registered since (extensions). A tray or section the layout
    names but nobody registered (an extension not loaded, or gone) is kept
    in the data and left out of what the window shows."""

    def __init__(self) -> None:
        self.homes: dict[str, tuple[str, ...]] = dict(DEFAULT_SECTIONS)
        self.trays: dict[str, list[str]] = {
            t: list(s) for t, s in DEFAULT_SECTIONS.items()}
        self.names: dict[str, str] = {}
        #: Sections the saved layout knew: one of them in no tray was taken
        #: out by the user, and stays out when its extension registers.
        self._known: set[str] = set(all_sections())

    # ---- reading -------------------------------------------------------------
    def sections(self) -> list[str]:
        """Every registered section, in the order of their home trays."""
        return [s for sections in self.homes.values() for s in sections]

    def home_of(self, section: str) -> str | None:
        return next((t for t, sections in self.homes.items()
                     if section in sections), None)

    def tray_of(self, section: str) -> str | None:
        """The tray showing ``section``; ``None`` when it is in none."""
        return next((t for t, sections in self.trays.items()
                     if section in sections), None)

    def custom_trays(self) -> list[str]:
        return [t for t in self.trays if is_custom(t)]

    def float_trays(self) -> list[str]:
        """The dialog windows: each a tray of its own, with no tab."""
        return [t for t in self.trays if is_float(t)]

    # ---- an extension's panel ------------------------------------------------
    def register(self, tray: str, sections) -> None:
        """A tray that turned up after the layout was read — an extension's
        panel — and the sections it comes with. Where the saved layout put
        them, they stay; one it never knew starts in its own tray."""
        sections = tuple(sections)
        self.homes[tray] = sections
        self.trays.setdefault(tray, [])
        for s in sections:
            if self.tray_of(s) is None and s not in self._known:
                self._put_home(s)
            self._known.add(s)

    # ---- editing -------------------------------------------------------------
    def new_tray(self, name: str) -> str:
        """A new, empty tray called ``name``; returns its id."""
        tray = CUSTOM_PREFIX + uuid.uuid4().hex[:8]
        while tray in self.trays:                       # pragma: no cover
            tray = CUSTOM_PREFIX + uuid.uuid4().hex[:8]
        self.trays[tray] = []
        self.names[tray] = name
        return tray

    def rename(self, tray: str, name: str) -> None:
        if not is_custom(tray) or tray not in self.trays:
            raise KeyError(tray)
        self.names[tray] = name

    def new_float(self) -> str:
        """A new, empty dialog window; returns its id."""
        tray = FLOAT_PREFIX + uuid.uuid4().hex[:8]
        while tray in self.trays:                       # pragma: no cover
            tray = FLOAT_PREFIX + uuid.uuid4().hex[:8]
        self.trays[tray] = []
        return tray

    def put_back(self, tray: str, origins: dict | None = None) -> list[str]:
        """A dialog window's sections back where they came from: the tray
        ``origins`` names for each, when it is still there and not a window
        itself, else at their factory place. The window goes. Returns
        them."""
        if not is_float(tray) or tray not in self.trays:
            raise KeyError(tray)
        sections = self.trays.pop(tray)
        for s in sections:
            origin = (origins or {}).get(s)
            if origin in self.trays and not is_float(origin):
                self.trays[origin].append(s)
            else:
                self._put_home(s)
        return sections

    def delete(self, tray: str) -> list[str]:
        """Remove one of the user's trays; its sections go back to the
        trays they came from, each at its factory place. Returns them."""
        if not is_custom(tray) or tray not in self.trays:
            raise KeyError(tray)
        sections = self.trays.pop(tray)
        self.names.pop(tray, None)
        for s in sections:
            self._put_home(s)
        return sections

    def set_section(self, tray: str, section: str, on: bool) -> None:
        """Manage Trays' check box: ``on`` moves the section into ``tray``
        (at its end) from wherever it was; off takes it out of ``tray``,
        leaving it in no tray."""
        self._check(tray, section)
        if on:
            if section not in self.trays[tray]:
                self._take_out(section)
                self.trays[tray].append(section)
        elif section in self.trays[tray]:
            self.trays[tray].remove(section)

    def place(self, section: str, tray: str, index: int) -> None:
        """Put ``section`` in ``tray`` at ``index`` — counted among the
        tray's sections without it, so the same list read with it taken
        out. Clamped to the ends."""
        self._check(tray, section)
        self._take_out(section)
        target = self.trays[tray]
        target.insert(max(0, min(index, len(target))), section)

    def _check(self, tray: str, section: str) -> None:
        if tray not in self.trays:
            raise KeyError(tray)
        if self.home_of(section) is None:
            raise KeyError(section)

    def _take_out(self, section: str) -> None:
        for sections in self.trays.values():
            if section in sections:
                sections.remove(section)

    def _put_home(self, section: str) -> None:
        """Back into the tray it comes from, before the first section that
        follows it in the factory order. A section with no known home (an
        extension's, while it is not loaded) is left out."""
        home = self.home_of(section)
        if home is None:
            # Forgotten, not «taken out»: back home when it registers.
            self._known.discard(section)
            return
        order = self.homes[home]
        after = set(order[order.index(section) + 1:])
        target = self.trays.setdefault(home, [])
        index = next((i for i, s in enumerate(target) if s in after),
                     len(target))
        target.insert(index, section)

    # ---- saving --------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "trays": [{"id": t, "sections": list(s),
                       **({"name": self.names[t]} if is_custom(t) else {})}
                      for t, s in self.trays.items()],
            # The sections known so far: one a later version (or a newly
            # installed extension) adds is not «taken out by the user».
            "known": sorted(self._known | set(self.sections())),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data) -> TrayLayout:
        """The layout :meth:`to_dict` wrote. A damaged value is left out —
        a section listed twice, a nameless tray of the user's, what is not
        text; a built-in section the save did not know yet starts in its
        own tray."""
        layout = cls()
        if not isinstance(data, dict) or not isinstance(data.get("trays"), list):
            return layout
        trays: dict[str, list[str]] = {t: [] for t in DEFAULT_SECTIONS}
        names: dict[str, str] = {}
        seen: set[str] = set()
        for entry in data["trays"]:
            if not isinstance(entry, dict):
                continue
            tray = entry.get("id")
            if not isinstance(tray, str) or not tray:
                continue
            if is_custom(tray):
                name = entry.get("name")
                if not isinstance(name, str) or not name.strip() \
                        or tray in names:
                    continue
                names[tray] = name
            trays.setdefault(tray, [])
            sections = entry.get("sections")
            for s in sections if isinstance(sections, list) else ():
                if isinstance(s, str) and s and s not in seen:
                    trays[tray].append(s)
                    seen.add(s)
        layout.trays, layout.names = trays, names
        known = data.get("known")
        layout._known = ({k for k in known if isinstance(k, str)}
                         if isinstance(known, list) else set(all_sections()))
        for s in all_sections():
            if s not in seen and s not in layout._known:
                layout._put_home(s)
        layout._known |= set(all_sections())
        return layout

    @classmethod
    def from_json(cls, text) -> TrayLayout:
        try:
            data = json.loads(text) if text else None
        except (TypeError, ValueError):
            data = None
        return cls.from_dict(data)
