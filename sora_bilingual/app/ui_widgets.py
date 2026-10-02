"""Small Qt adapters that retain source messages for live language changes."""

import math

from PySide6 import QtWidgets as Qt
from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from sora_bilingual.app.i18n import tr

SOURCE_ROLE = 356

# Game artwork is bundled locally; no game discovery or network is needed to draw.
NATIVE_THEME = """
QWidget { background: #f4efe2; color: #33291f; font-size: 13px; }
QWidget#bar, QWidget#panel { background: #f8f3e8; border: 1px solid #b89555; border-radius: 10px; }
QWidget#statusFooter { background: #eee4cf; border: 1px solid #d4bd88; border-radius: 7px; }
QLabel { background: transparent; border: none; }
QLabel#brand { color: #7a5424; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#title, QLabel#pageTitle { color: #70451b; font-size: 21px; font-weight: 700; }
QLabel#sectionTitle { color: #775226; font-size: 14px; font-weight: 700; padding-top: 4px; }
QLabel#detail, QLabel#helpText { color: #685b4b; font-size: 12px; }
QLabel#status { color: #176b6b; font-size: 14px; font-weight: 700; }
QLabel#statusMarker { font-size: 15px; font-weight: 700; }
QLabel#liveBadge { color: #0b6663; background: #d5eee7; border: 1px solid #91c9bc; border-radius: 9px; padding: 3px 8px; font-weight: 700; }
QPushButton { background: #fdf9ef; border: 1px solid #b89555; border-radius: 6px; padding: 8px 12px; min-height: 18px; }
QPushButton:hover { background: #e8f3ef; border-color: #167b78; }
QPushButton:pressed { background: #d2e8e1; border-color: #0e625e; }
QPushButton:focus, QComboBox:focus, QDoubleSpinBox:focus, QSlider:focus, QCheckBox:focus, QRadioButton:focus { border: 2px solid #167b78; }
QPushButton#primaryAction { background: #167b78; color: #ffffff; border-color: #0e625e; font-weight: 700; }
QPushButton#primaryAction:hover { background: #0e625e; }
QPushButton:disabled { color: #978a78; background: #eee9dd; border-color: #d1c4ad; }
QComboBox, QDoubleSpinBox { background: #fffdf7; border: 1px solid #cbb782; border-radius: 5px; padding: 6px 8px; min-height: 20px; }
QComboBox::drop-down { border-left: 1px solid #cbb782; width: 24px; }
QComboBox QAbstractItemView { background: #fffdf7; color: #33291f; selection-background-color: #d8a935; selection-color: #33291f; }
QTabWidget::pane { border: 1px solid #d5c193; border-radius: 8px; top: -1px; }
QTabBar::tab { background: #e9dfcc; color: #685638; padding: 10px 18px; margin: 0 4px 0 0; border: 1px solid #d2bc88; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:hover { background: #e4f0eb; color: #145d5b; }
QTabBar::tab:selected { background: #d9ac3a; color: #37260d; border-color: #b78922; font-weight: 700; }
QCheckBox { spacing: 9px; padding: 7px 0; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #a98649; border-radius: 4px; background: #fffdf7; }
QCheckBox::indicator:checked { background: #167b78; border-color: #0e625e; }
QRadioButton { spacing: 9px; padding: 7px 0; }
QRadioButton::indicator { width: 17px; height: 17px; border: 1px solid #a98649; border-radius: 9px; background: #fffdf7; }
QRadioButton::indicator:checked { border: 5px solid #167b78; background: #fffdf7; }
QSlider::groove:horizontal { background: #dacdb3; height: 6px; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #1c8b86; border-radius: 3px; }
QSlider::handle:horizontal { background: #d9ac3a; border: 1px solid #946d1b; width: 14px; margin: -5px 0; border-radius: 7px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #eee6d7; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: #bca979; border-radius: 4px; min-height: 28px; }
/* Handbook shell. Surfaces paint the original game textures underneath. */
QWidget { background: transparent; color: #2b383a; }
QWidget#panel, QWidget#bar { background: transparent; border: none; }
QLabel#pageTitle { color: #565c36; font-size: 24px; padding-bottom: 7px; }
QLabel#navGroup { color: #fff2ce; font-weight: 600; padding: 3px 12px 5px 28px; }
QLabel#sampleName { color:#7e7838; font-weight:700; font-size:14px; }
QLabel#appearanceTitle { font-weight:700; }
QRadioButton#appearanceChoice { background:#f8f7ee; border:1px solid #aeb3a2; border-radius:4px; padding:10px; }
QRadioButton#appearanceChoice:checked, QRadioButton#appearanceChoice:focus { border:2px solid #667444; }
QRadioButton#appearanceChoice:hover { background:#edf0e5; }
QLabel#brand { color: #fff1b9; font-size: 18px; letter-spacing: 2px; }
QLabel#status { color: #fff3d0; font-size: 12px; }
QLabel#detail, QLabel#helpText { color: #627071; }
QTabWidget::pane { border: none; }
QWidget#statusFooter { background: #e6e9dc; border: 1px solid #c4c9b2; border-radius: 3px; }
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; border: 2px solid #777c52; border-radius: 9px; background: transparent; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border: 2px solid #667444; background: #667444; }
QPushButton { border-radius: 3px; border-color: #aeb3a2; background: #f8f7ee; }
QPushButton#primaryAction { background: #285669; border-color: #456c78; }
QPushButton#headerButton { color: #fff5da; background: transparent; border: 1px solid #a5aa8a; padding: 5px 10px; }
QPushButton#headerButton:hover { background: #375666; }
QPushButton#headerButton[updateAvailable="true"] { color: #473d21; background: #e7ce7a; border-color: #f5e8b6; }
QMenu, QDialog { background: #f5f2e6; }
QMenu { border: 1px solid #9a9979; padding: 5px; }
QMenu::item { padding: 8px 24px; }
QMenu::item:selected { background: #d9e3d9; }
QToolTip { color: #f8f3da; background: #254657; border: 1px solid #b6ae7b; padding: 5px; }
"""


def apply_native_theme(app):
    """Apply the paper-panel visual system to standalone and overlay windows."""
    app.setStyleSheet(NATIVE_THEME)


class Text:
    def __init__(self, text="", *args, **kwargs):
        super().__init__(tr(text), *args, **kwargs)
        self.setProperty("ui_source", text)

    def setText(self, text):
        self.setProperty("ui_source", text)
        super().setText(tr(text))

    def clear(self):
        self.setText("")


class QLabel(Text, Qt.QLabel):
    pass


class QPushButton(Text, Qt.QPushButton):
    pass


class QCheckBox(Text, Qt.QCheckBox):
    pass


class QRadioButton(Text, Qt.QRadioButton):
    pass


class QComboBox(Qt.QComboBox):
    def wheelEvent(self, event):
        # Scrolling a settings page must not change a saved selection, even
        # when this combo has focus. Its opened popup still scrolls normally.
        event.ignore()

    def addItem(self, text, userData=None):
        super().addItem(tr(text), userData)
        self.setItemData(self.count() - 1, text, SOURCE_ROLE)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Text), 2))
        center_x = self.width() - 13
        center_y = self.height() // 2 - 1
        painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)
        painter.end()


class QDoubleSpinBox(Qt.QDoubleSpinBox):
    """Editable value beside a slider; no duplicate step buttons."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setButtonSymbols(Qt.QAbstractSpinBox.ButtonSymbols.NoButtons)


class ColorButton(Qt.QPushButton):
    """A compact, keyboard-accessible RGBA selector stored as normalized floats."""

    colorChanged = Signal(tuple)
    opacityChanged = Signal(float)

    def __init__(self, color=(0.9, 0.9, 0.9), opacity=1.0, parent=None):
        super().__init__(parent)
        self.setObjectName("colorButton")
        self.setProperty("ui_tooltip", "选择副语言颜色")
        self.setProperty("ui_accessible_name", "副语言颜色")
        self.setProperty(
            "ui_accessible_description", "打开颜色选择器，保存副语言 RGB 颜色和透明度。"
        )
        self.setAccessibleDescription(tr(self.property("ui_accessible_description")))
        self.clicked.connect(self._choose)
        self._color = (0.9, 0.9, 0.9)
        self._opacity = 1.0
        self.set_color(color, opacity=opacity)

    def color(self) -> tuple[float, float, float]:
        return self._color

    def opacity(self) -> float:
        return self._opacity

    def set_color(self, value, *, opacity=None, emit=False) -> None:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError("副语言颜色必须是三个 0 到 1 的数值")
        color = tuple(float(component) for component in value)
        if any(
            not math.isfinite(component) or component < 0 or component > 1 for component in color
        ):
            raise ValueError("副语言颜色必须在 0 到 1 之间")
        new_opacity = self._opacity if opacity is None else float(opacity)
        if not math.isfinite(new_opacity) or not 0 <= new_opacity <= 1:
            raise ValueError("副语言透明度必须在 0 到 1 之间")
        opacity_changed = new_opacity != self._opacity
        self._color = color
        self._opacity = new_opacity
        qcolor = QColor.fromRgbF(*color, new_opacity)
        rgb = tuple(round(component * 255) for component in color)
        ink = "#33291f" if qcolor.lightnessF() >= 0.55 else "#ffffff"
        self.setText("RGB " + " / ".join(map(str, rgb)) + f" · {round(new_opacity * 100)}%")
        self.setStyleSheet(
            "QPushButton#colorButton { background: %s; color: %s; border: 1px solid #b89555; "
            "border-radius: 6px; padding: 8px 12px; min-height: 18px; font-weight: 700; } "
            "QPushButton#colorButton:focus { border: 2px solid #167b78; }" % (qcolor.name(), ink)
        )
        if emit:
            self.colorChanged.emit(color)
            if opacity_changed:
                self.opacityChanged.emit(new_opacity)

    def _choose(self) -> None:
        chosen = Qt.QColorDialog.getColor(
            QColor.fromRgbF(*self._color, self._opacity),
            self,
            tr("选择副语言颜色"),
            Qt.QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if chosen.isValid():
            self.set_color(
                (chosen.redF(), chosen.greenF(), chosen.blueF()), opacity=chosen.alphaF(), emit=True
            )


class QTabWidget(Qt.QTabWidget):
    def addTab(self, widget, text):
        widget.setProperty("ui_tab_source", text)
        return super().addTab(widget, tr(text))


class QFormLayout(Qt.QFormLayout):
    def addRow(self, *args):
        if args and isinstance(args[0], str):
            label = QLabel(args[0])
            label.setWordWrap(True)
            args = (label, *args[1:])
        return super().addRow(*args)


def retranslate(root):
    for widget in [root, *root.findChildren(Qt.QWidget)]:
        if isinstance(widget, Text):
            widget.setText(widget.property("ui_source") or "")
        if isinstance(widget, QComboBox):
            with QSignalBlocker(widget):
                for i in range(widget.count()):
                    widget.setItemText(i, tr(widget.itemData(i, SOURCE_ROLE)))
        if isinstance(widget, QTabWidget):
            for i in range(widget.count()):
                widget.setTabText(i, tr(widget.widget(i).property("ui_tab_source")))
        for method, setter, prop in [
            ("toolTip", "setToolTip", "ui_tooltip"),
            ("windowTitle", "setWindowTitle", "ui_title"),
            ("accessibleName", "setAccessibleName", "ui_accessible_name"),
            ("accessibleDescription", "setAccessibleDescription", "ui_accessible_description"),
        ]:
            source = widget.property(prop)
            if source is None:
                source = getattr(widget, method)()
                widget.setProperty(prop, source)
            if source:
                getattr(widget, setter)(tr(source))
