"""Small Qt adapters that retain source messages for live language changes."""

from PySide6 import QtWidgets as Qt
from PySide6.QtCore import QSignalBlocker
from sora_bilingual.app.i18n import tr

SOURCE_ROLE = 356


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


class QComboBox(Qt.QComboBox):
    def addItem(self, text, userData=None):
        super().addItem(tr(text), userData)
        self.setItemData(self.count() - 1, text, SOURCE_ROLE)


class QTabWidget(Qt.QTabWidget):
    def addTab(self, widget, text):
        widget.setProperty("ui_tab_source", text)
        return super().addTab(widget, tr(text))


class QFormLayout(Qt.QFormLayout):
    def addRow(self, *args):
        if args and isinstance(args[0], str):
            args = (QLabel(args[0]), *args[1:])
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
        ]:
            source = widget.property(prop)
            if source is None:
                source = getattr(widget, method)()
                widget.setProperty(prop, source)
            if source:
                getattr(widget, setter)(tr(source))
