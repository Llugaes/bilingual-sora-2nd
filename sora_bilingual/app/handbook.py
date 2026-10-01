"""Cached game artwork and small presentation widgets for the handbook UI.

No game access, image decoding workers, or network activity at window creation.
The seven PNG slices are shipped with the application; see assets/handbook/NOTICE.
"""

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QSize, QEvent
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QBoxLayout, QLayout

from sora_bilingual.app.ui_widgets import QPushButton
from sora_bilingual.app import handbook_resources  # noqa: F401 - registers Qt resources

ASSETS = Path(__file__).parent / "assets" / "handbook"


@lru_cache(maxsize=8)
def artwork(name):
    return QPixmap(f":/handbook/{name}.png")


def draw_slice(painter, target, name, inset, border=None):
    """Nine-slice panels keep metal corners round instead of stretching them."""
    pixmap = artwork(name)
    if pixmap.isNull():
        painter.fillRect(target, QColor("#eeeade"))
        return
    ix, iy = inset if isinstance(inset, tuple) else (inset, inset)
    bx, by = border or (ix, iy)
    bx, by = min(bx, target.width() // 2), min(by, target.height() // 2)
    sx = (0, ix, pixmap.width() - ix, pixmap.width())
    sy = (0, iy, pixmap.height() - iy, pixmap.height())
    dx = (target.x(), target.x() + bx, target.right() + 1 - bx, target.right() + 1)
    dy = (target.y(), target.y() + by, target.bottom() + 1 - by, target.bottom() + 1)
    for y in range(3):
        for x in range(3):
            painter.drawPixmap(
                QRect(dx[x], dy[y], dx[x + 1] - dx[x], dy[y + 1] - dy[y]),
                pixmap,
                QRect(sx[x], sy[y], sx[x + 1] - sx[x], sy[y + 1] - sy[y]),
            )


class SkinSurface(QWidget):
    def __init__(self, skin, parent=None, flags=Qt.WindowType.Widget):
        super().__init__(parent, flags)
        self.skin = skin

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.skin == "handbook":
            painter.drawPixmap(self.rect(), artwork(self.skin))
        else:
            if self.skin == "dialogue-frame":
                painter.fillRect(self.rect().adjusted(4, 4, -4, -4), QColor("#faf8ed"))
                draw_slice(painter, self.rect(), self.skin, 28, (17, 17))
            else:
                draw_slice(painter, self.rect(), self.skin, (48, 18), (32, 13))


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
        self.setFixedHeight(49)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        skin = "blue-bar-selected" if self.isChecked() else "blue-bar"
        painter.drawPixmap(self.rect().adjusted(7, 2, -1, -2), artwork(skin))
        if self.isChecked():
            painter.drawPixmap(QRect(0, self.height() // 2 - 6, 23, 12), artwork("cursor"))
        painter.setPen(QColor("#fff5d2"))
        font = self.font()
        font.setBold(self.isChecked())
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(28, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter, self.text()
        )
        if self.hasFocus():
            painter.setPen(QPen(QColor("#efd982"), 1, Qt.PenStyle.DotLine))
            painter.drawRect(self.rect().adjusted(22, 9, -9, -9))


def gear_icon():
    return QIcon(artwork("gear"))
