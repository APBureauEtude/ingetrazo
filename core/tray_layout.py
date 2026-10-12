# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Which sections each side tray holds, and in what order — the data behind
Window ▸ Manage Trays.

SketchUp's words: a *tray* is a tab of the side bar, a *dialog* is one of
the folding sections inside it (Entity info, Layers, Materials…). The
built-in trays start with their factory sections; the user can make trays
of their own, put any section in any tray (a section is in one tray at a
time), take one out of every tray, and reorder the sections of a tray.

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
    "tray_properties": ("entity_info", "layers", "scenes", "materials",
                        "components", "parts"),
    "tray_bim": ("bim",),
    "tray_georef": ("base_map", "survey"),
}

#: Every tray the user makes is named ``tray_user_<hex>``: never reused, so
#: a deleted tray's saved place or hidden state can't land on a new one.
CUSTOM_PREFIX = "tray_user_"


def all_sections() -> list[str]:
    """Every section id, in the factory order."""
    return [s for sections in DEFAULT_SECTIONS.values() for s in sections]


def home_of(section: str) -> str:
    """The built-in tray a section comes from."""
    return next(t for t, sections in DEFAULT_SECTIONS.items()
                if section in sections)


def is_custom(tray: str) -> bool:
    return tray.startswith(CUSTOM_PREFIX)


class TrayLayout:
    """Tray id → its section ids in order, built-in trays first, then the
    user's in the order they were made; plus the user's trays' names."""

    def __init__(self) -> None:
        self.trays: dict[str, list[str]] = {
            t: list(s) for t, s in DEFAULT_SECTIONS.items()}
        self.names: dict[str, str] = {}

    # ---- reading -------------------------------------------------------------
    def tray_of(self, section: str) -> str | None:
        """The tray showing ``section``; ``None`` when it is in none."""
        return next((t for t, sections in self.trays.items()
                     if section in sections), None)

    def custom_trays(self) -> list[str]:
        return [t for t in self.trays if is_custom(t)]

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

    def delete(self, tray: str) -> list[str]:
        """Remove one of the user's trays; its sections go back to the
        built-in trays they came from, each at its factory place. Returns
        them."""
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
        if tray not in self.trays or section not in all_sections():
            raise KeyError(tray if tray not in self.trays else section)
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
        if tray not in self.trays or section not in all_sections():
            raise KeyError(tray if tray not in self.trays else section)
        self._take_out(section)
        target = self.trays[tray]
        target.insert(max(0, min(index, len(target))), section)

    def _take_out(self, section: str) -> None:
        for sections in self.trays.values():
            if section in sections:
                sections.remove(section)

    def _put_home(self, section: str) -> None:
        """Back into its built-in tray, before the first section that
        follows it in the factory order."""
        home = home_of(section)
        order = DEFAULT_SECTIONS[home]
        after = set(order[order.index(section) + 1:])
        target = self.trays[home]
        index = next((i for i, s in enumerate(target) if s in after),
                     len(target))
        target.insert(index, section)

    # ---- saving --------------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps({
            "trays": [{"id": t, "sections": list(s),
                       **({"name": self.names[t]} if is_custom(t) else {})}
                      for t, s in self.trays.items()],
            # The sections this version knew: one a later version adds is
            # not «taken out by the user» and starts in its own tray.
            "known": all_sections(),
        })

    @classmethod
    def from_json(cls, text) -> TrayLayout:
        """The layout saved by :meth:`to_json`. Whatever does not fit — a
        section or tray this version does not have, a section listed
        twice, a damaged string — is left out; a section that did not
        exist when it was saved starts in its own tray."""
        layout = cls()
        try:
            data = json.loads(text) if text else None
        except (TypeError, ValueError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("trays"), list):
            return layout
        known_sections = set(all_sections())
        trays: dict[str, list[str]] = {t: [] for t in DEFAULT_SECTIONS}
        names: dict[str, str] = {}
        seen: set[str] = set()
        for entry in data["trays"]:
            if not isinstance(entry, dict):
                continue
            tray = entry.get("id")
            if not isinstance(tray, str):
                continue
            if is_custom(tray):
                name = entry.get("name")
                if not isinstance(name, str) or not name.strip() \
                        or tray in names:
                    continue
                names[tray] = name
                trays[tray] = []
            elif tray not in DEFAULT_SECTIONS:
                continue
            sections = entry.get("sections")
            for s in sections if isinstance(sections, list) else ():
                if isinstance(s, str) and s in known_sections and s not in seen:
                    trays[tray].append(s)
                    seen.add(s)
        layout.trays, layout.names = trays, names
        known = data.get("known")
        known = ({k for k in known if isinstance(k, str)}
                 if isinstance(known, list) else known_sections)
        for s in all_sections():
            if s not in seen and s not in known:
                layout._put_home(s)
        return layout
