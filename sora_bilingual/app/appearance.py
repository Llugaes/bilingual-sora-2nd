"""Desktop-only appearance definitions; no game configuration or runtime work."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Surface:
    asset: str
    inset: tuple
    border: tuple


@dataclass(frozen=True)
class Appearance:
    key: str
    title: str
    description: str
    emblem: str
    bar: Surface
    selected: Surface
    card: Surface
    colors: dict


PAPER_CARD = Surface("dialogue-frame", (28, 28), (17, 17))
TECH_FRAME = Surface("tech-frame", (52, 48), (20, 17))
APPEARANCES = {
    "sky": Appearance(
        "sky",
        "空之轨迹（默认）",
        "深蓝金属、皮革书脊与浅色纸页。",
        "guild-emblem",
        Surface("blue-bar", (48, 18), (32, 13)),
        Surface("blue-bar-selected", (48, 18), (32, 13)),
        PAPER_CARD,
        {},
    ),
    "bracer": Appearance(
        "bracer",
        "游击士手册",
        "协会木纹、铜色徽章与酒红选择条。",
        "bronze-emblem",
        Surface("red-bar", (52, 18), (28, 13)),
        Surface("red-bar-selected", (52, 18), (28, 13)),
        PAPER_CARD,
        dict(
            text="#403326",
            heading="#663a29",
            muted="#6b5746",
            accent="#854a38",
            field="#fcf5e6",
            hover="#eadbc1",
            edge="#9e8465",
            track="#d5c5a8",
            header="#fff3d6",
            nav="#fff1cf",
            sample="#79602e",
            card="#faf8ed",
        ),
    ),
    "orbment": Appearance(
        "orbment",
        "导力工房",
        "导力菜单的蓝钢、回路纹理与机械圆盘。",
        "orbment-emblem",
        TECH_FRAME,
        TECH_FRAME,
        Surface("dark-frame", (28, 28), (17, 17)),
        dict(
            text="#e8f0f3",
            heading="#bdeaf4",
            muted="#bac9d0",
            accent="#76dbea",
            field="#253a48",
            hover="#345567",
            edge="#829aa5",
            track="#4b6470",
            header="#edfbff",
            nav="#e2f4fa",
            sample="#f0dba4",
            card="#343434",
        ),
    ),
}
DEFAULT_APPEARANCE = "sky"


def appearance(key):
    return APPEARANCES.get(key if isinstance(key, str) else "", APPEARANCES[DEFAULT_APPEARANCE])


def appearance_for(widget):
    while widget is not None:
        key = widget.property("appearance")
        if key:
            return appearance(key)
        widget = widget.parentWidget()
    return appearance(DEFAULT_APPEARANCE)


def stylesheet(theme):
    if not theme.colors:
        return ""
    return """
QWidget {{ color:{text}; }}
QLabel#pageTitle, QLabel#sectionTitle {{ color:{heading}; }}
QLabel#detail, QLabel#helpText {{ color:{muted}; }}
QLabel#navGroup {{ color:{nav}; }}
QLabel#brand, QLabel#status {{ color:{header}; }}
QLabel#sampleName {{ color:{sample}; }}
QPushButton {{ color:{text}; background:{field}; border-color:{edge}; }}
QPushButton:hover {{ background:{hover}; border-color:{accent}; }}
QPushButton:pressed {{ background:{hover}; }}
QPushButton:disabled {{ color:{muted}; background:{track}; }}
QPushButton#primaryAction {{ background:{accent}; color:{field}; border-color:{edge}; }}
QPushButton#primaryAction:hover {{ background:{heading}; }}
QPushButton#headerButton {{ color:{header}; background:transparent; border-color:{edge}; }}
QPushButton#headerButton:hover {{ color:{text}; background:{hover}; }}
QPushButton#headerButton[updateAvailable="true"] {{ color:#473d21; background:#e7ce7a; border-color:#f5e8b6; }}
QComboBox, QDoubleSpinBox {{ color:{text}; background:{field}; border-color:{edge}; }}
QComboBox::drop-down {{ border-color:{edge}; }}
QComboBox QAbstractItemView {{ color:{text}; background:{field}; selection-background-color:{hover}; selection-color:{text}; }}
QCheckBox::indicator, QRadioButton::indicator {{ border-color:{edge}; background:transparent; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ border-color:{accent}; background:{accent}; }}
QPushButton:focus, QComboBox:focus, QDoubleSpinBox:focus, QRadioButton:focus, QCheckBox:focus {{ border-color:{accent}; }}
QSlider::groove:horizontal {{ background:{track}; }}
QSlider::sub-page:horizontal, QSlider::handle:horizontal {{ background:{accent}; }}
QScrollBar:vertical {{ background:{field}; }}
QScrollBar::handle:vertical {{ background:{edge}; }}
QWidget#statusFooter {{ color:{text}; background:{field}; border-color:{edge}; }}
QLabel#liveBadge {{ color:#0b6663; background:#d5eee7; border-color:#91c9bc; }}
QRadioButton#appearanceChoice {{ background:{field}; border-color:{edge}; }}
QRadioButton#appearanceChoice:checked, QRadioButton#appearanceChoice:focus {{ border-color:{accent}; }}
QRadioButton#appearanceChoice:hover {{ background:{hover}; }}
QMenu, QDialog {{ color:{text}; background:{field}; }}
QMenu::item:selected {{ background:{hover}; }}
""".format(**theme.colors)


def apply_appearance(widget, key):
    theme = appearance(key)
    widget.setProperty("appearance", theme.key)
    widget.setStyleSheet(stylesheet(theme))
    widget.update()
