# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Field-of-view editor shared by the 3D view's Camera menu."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr


class FieldOfViewDialog(QDialog):
    """Edit the lens angle by typing it or dragging a live slider."""

    def __init__(self, parent: QWidget, value: float, minimum: float,
                 maximum: float, preview: Callable[[float], object]) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Field of view"))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Field of view in degrees (10–120):"), self))

        self.spin = QDoubleSpinBox(self)
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(0)
        self.spin.setSuffix("°")
        self.spin.setValue(value)
        layout.addWidget(self.spin)

        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(round(minimum), round(maximum))
        self.slider.setValue(round(value))
        layout.addWidget(self.slider)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(
            lambda degrees: self.slider.setValue(round(degrees)))
        self.spin.valueChanged.connect(preview)

        self.spin.setFocus()
        self.spin.selectAll()

    def value(self) -> float:
        """Return the angle currently shown by the editor."""
        return float(self.spin.value())
