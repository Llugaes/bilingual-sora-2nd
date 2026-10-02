"""Cached game artwork and small presentation widgets for the handbook UI.

No game access, image decoding workers, or network activity at window creation.
The PNG slices are shipped with the application; see assets/handbook/NOTICE.
"""

from functools import lru_cache
from math import ceil
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, Qt, QSize, QEvent
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QTextLayout, QTextOption
from PySide6.QtWidgets import QWidget, QBoxLayout, QLayout, QSizePolicy, QHBoxLayout, QVBoxLayout

from sora_bilingual.app.ui_widgets import QPushButton, QRadioButton, QLabel
from sora_bilingual.app.appearance import appearance, appearance_for
from sora_bilingual.app import handbook_resources  # noqa: F401 - registers Qt resources

ASSETS = Path(__file__).parent / "assets" / "handbook"

# Artwork and widgets share the same column geometry at every window width/DPI.
PANEL_INSET = 15
NAVIGATION_WIDTH = 170
CONTENT_GAP = 22
PAGE_INSET = 16
PAGE_LEFT = PANEL_INSET + NAVIGATION_WIDTH + CONTENT_GAP // 2
CONTENT_LEFT = NAVIGATION_WIDTH + CONTENT_GAP + PAGE_INSET


@lru_cache(maxsize=32)
def artwork(name):
    return QPixmap(f":/handbook/{name}.png")


def draw_slice(painter, target, name, inset, border=None):
    """Preserve panel edges; insets accept a scalar, x/y, or left/top/right/bottom."""
    pixmap = artwork(name)
    if pixmap.isNull():
        painter.fillRect(target, QColor("#eeeade"))
        return

    def edges(value):
        if isinstance(value, int):
            return (value,) * 4
        return value * 2 if len(value) == 2 else value

    left, top, right, bottom = edges(inset)
    bl, bt, br, bb = edges(border or inset)
    bl, br = min(bl, target.width() // 2), min(br, target.width() // 2)
    bt, bb = min(bt, target.height() // 2), min(bb, target.height() // 2)
    sx = (0, left, pixmap.width() - right, pixmap.width())
    sy = (0, top, pixmap.height() - bottom, pixmap.height())
    dx = (target.x(), target.x() + bl, target.right() + 1 - br, target.right() + 1)
    dy = (target.y(), target.y() + bt, target.bottom() + 1 - bb, target.bottom() + 1)
    for y in range(3):
        for x in range(3):
            painter.drawPixmap(
                QRect(dx[x], dy[y], dx[x + 1] - dx[x], dy[y + 1] - dy[y]),
                pixmap,
                QRect(sx[x], sy[y], sx[x + 1] - sx[x], sy[y + 1] - sy[y]),
            )


def paint_surface(painter, target, skin, theme):
    """One renderer for windows, controls, the compact bar and chooser previews."""
    if skin == "handbook":
        if theme.key == "sky":
            draw_slice(painter, target, skin, (280, 36, 42, 36), (PAGE_LEFT, 18, 21, 18))
        else:
            paper = target.adjusted(PAGE_LEFT, 14, -15, -6)
            if theme.key == "bracer":
                draw_slice(painter, target, "guild-cover", (40, 28), (18, 18))
                draw_slice(painter, paper, "guild-page", (80, 45), (17, 17))
                painter.save()
                painter.setOpacity(0.24)
                painter.drawPixmap(paper.adjusted(20, 20, -20, -20), artwork("camp-background"))
                painter.restore()
            else:
                draw_slice(painter, target, theme.bar.asset, theme.bar.inset, theme.bar.border)
                painter.save()
                painter.setOpacity(0.3)
                painter.drawPixmap(
                    QRect(target.x() + 18, target.y() + 90, PAGE_LEFT - 30, target.height() - 114),
                    artwork("circuit"),
                )
                painter.restore()
                painter.fillRect(paper, QColor(theme.colors["card"]))
                draw_slice(painter, paper, theme.card.asset, theme.card.inset, theme.card.border)
        return
    surface = (
        theme.card
        if skin == "dialogue-frame"
        else (theme.selected if skin == "blue-bar-selected" else theme.bar)
    )
    if skin == "dialogue-frame":
        painter.fillRect(target.adjusted(4, 4, -4, -4), QColor(theme.colors.get("card", "#faf8ed")))
    draw_slice(painter, target, surface.asset, surface.inset, surface.border)
    if skin == "blue-bar-selected" and theme.key == "orbment":
        painter.save()
        painter.setPen(QPen(QColor(theme.colors["accent"]), 2))
        painter.drawLine(
            target.left() + 22, target.bottom() - 5, target.right() - 22, target.bottom() - 5
        )
        painter.restore()


class SkinSurface(QWidget):
    def __init__(self, skin, parent=None, flags=Qt.WindowType.Widget):
        super().__init__(parent, flags)
        self.skin = skin

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        paint_surface(painter, self.rect(), self.skin, appearance_for(self))


class AppearancePreview(QWidget):
    def __init__(self, key):
        super().__init__()
        self.key = key
        self.setFixedHeight(82)
        self.setMinimumWidth(96)
        self.setMaximumWidth(128)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def sizeHint(self):
        return QSize(128, 82)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.scale(self.width() / 850, self.height() / 720)
        theme = appearance(self.key)
        paint_surface(painter, QRect(0, 0, 850, 720), "handbook", theme)
        paint_surface(painter, QRect(15, 14, 820, 65), "blue-bar", theme)
        painter.drawPixmap(QRect(38, 24, 42, 45), artwork(theme.emblem))
        for i in range(4):
            paint_surface(
                painter,
                QRect(22, 163 + i * 65, 162, 49),
                "blue-bar-selected" if i == 0 else "blue-bar",
                theme,
            )
        paint_surface(painter, QRect(224, 193, 568, 150), "dialogue-frame", theme)
        painter.setPen(QPen(QColor(theme.colors.get("text", "#566252")), 8))
        for y, right in ((137, 503), (240, 686), (280, 547), (390, 645), (432, 583)):
            painter.drawLine(245, y, right, y)


class AppearanceChoice(QRadioButton):
    """A native radio control with a full-card hit target and a real skin preview."""

    def __init__(self, theme):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setObjectName("appearanceChoice")
        self.setProperty("ui_accessible_name", theme.title)
        self.setAccessibleName(theme.title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(38, 8, 12, 8)
        row.setSpacing(14)
        row.addWidget(AppearancePreview(theme.key))
        words = QVBoxLayout()
        words.setSpacing(5)
        words.addStretch()
        title = QLabel(theme.title)
        title.setWordWrap(True)
        title.setObjectName("appearanceTitle")
        description = QLabel(theme.description)
        description.setWordWrap(True)
        description.setObjectName("helpText")
        for label in (title, description):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            words.addWidget(label)
        words.addStretch()
        row.addLayout(words, 1)

    def hitButton(self, position):
        return self.rect().contains(position)

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()


class ChoiceRow(QWidget):
    """Keep the two mode cards side by side when labels fit; stack for large text."""

    def __init__(self):
        super().__init__()
        row = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def _sizes(self):
        return [
            self.layout().itemAt(i).widget().minimumSizeHint() for i in range(self.layout().count())
        ]

    def sizeHint(self):
        sizes = self._sizes()
        width = sum(s.width() for s in sizes) + max(0, self.layout().spacing())
        return QSize(width, self.heightForWidth(width))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        sizes = self._sizes()
        if not sizes:
            return 0
        gap = max(0, self.layout().spacing()) * (len(sizes) - 1)
        if width < sum(s.width() for s in sizes) + gap:
            return sum(s.height() for s in sizes) + gap
        return max(s.height() for s in sizes)

    def minimumSizeHint(self):
        sizes = self._sizes()
        return QSize(
            max((s.width() for s in sizes), default=0), max((s.height() for s in sizes), default=0)
        )

    def _adapt(self):
        needed = sum(s.width() for s in self._sizes()) + max(0, self.layout().spacing())
        self.layout().setDirection(
            QBoxLayout.Direction.TopToBottom
            if self.width() < needed
            else QBoxLayout.Direction.LeftToRight
        )
        height = self.heightForWidth(self.width())
        if self.minimumHeight() != height:
            self.setFixedHeight(height)

    def event(self, event):
        if event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Show):
            self._adapt()
        return super().event(event)

    def resizeEvent(self, event):
        self._adapt()
        super().resizeEvent(event)


class BadgeButton(QPushButton):
    """Notification is actual update state, never an unread-message counter."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._notice = False

    def set_notice(self, available):
        self._notice = bool(available)
        self.setProperty("updateAvailable", self._notice)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._notice:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#fff1c0"), 1))
            painter.setBrush(QColor("#ce3d42"))
            painter.drawEllipse(self.width() - 11, 2, 8, 8)


class NavigationButton(QPushButton):
    def __init__(self, title):
        super().__init__(title)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(49)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def label_layout(self, width, selected=None):
        """One wrapping calculation for sizing and painting, including long words."""
        font = self.font()
        font.setBold(self.isChecked() if selected is None else selected)
        text = QTextLayout(self.text(), font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        text.setTextOption(option)
        text.beginLayout()
        height = 0
        while (line := text.createLine()).isValid():
            line.setLineWidth(max(1, width - 40))
            line.setPosition(QPointF(0, height))
            height += line.height()
        text.endLayout()
        return text

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        # Selecting a page must not make its label clip.
        text = self.label_layout(width, selected=True)
        return max(49, ceil(text.boundingRect().height()) + 20)

    def sizeHint(self):
        return QSize(NAVIGATION_WIDTH, self.heightForWidth(NAVIGATION_WIDTH))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        skin = "blue-bar-selected" if self.isChecked() else "blue-bar"
        theme = appearance_for(self)
        # Keep the existing default tab corners; other skins share their bar renderer.
        if theme.key == "sky":
            draw_slice(painter, self.rect().adjusted(7, 2, -1, -2), skin, (48, 18), (18, 13))
        else:
            paint_surface(painter, self.rect().adjusted(7, 2, -1, -2), skin, theme)
        if self.isChecked():
            painter.drawPixmap(QRect(0, self.height() // 2 - 6, 23, 12), artwork("cursor"))
        painter.setPen(QColor(theme.colors.get("nav", "#fff5d2")))
        text = self.label_layout(self.width())
        text.draw(painter, QPointF(28, (self.height() - text.boundingRect().height()) / 2))
        if self.hasFocus():
            painter.setPen(QPen(QColor("#efd982"), 1, Qt.PenStyle.DotLine))
            painter.drawRect(self.rect().adjusted(22, 9, -9, -9))


def gear_icon():
    return QIcon(artwork("gear"))
