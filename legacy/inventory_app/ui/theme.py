"""Light and dark colour themes, the application stylesheet and line icons."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from inventory_app.paths import resource_path

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#d3e5ec", "sidebar": "#2f5d6e", "sidebar_hover": "#3b6b7d",
        "sidebar_text": "#e8f1f4", "sidebar_muted": "#a9c3cc", "nav_active_text": "#2f5d6e",
        "card": "#f5fafc", "input_bg": "#ffffff", "border": "#c5dae2", "border_strong": "#9fbcc7",
        "text": "#1f3b47", "heading": "#1f4a5a", "muted": "#5e7a86", "hover": "#e4f0f4",
        "alt_row": "#edf5f8", "selection": "#c4dde6", "accent": "#3f6f80", "on_accent": "#ffffff",
        "tile_bg": "#f2f8f6", "tile_border": "#c3dcd4", "icon_bg": "#cfe8df", "icon_fg": "#3d7a68",
        "warn_bg": "#fbefe9", "warn_border": "#e7c2b0", "warn_icon_bg": "#f6d9cb", "warn_fg": "#b5643f",
        "danger": "#c0392b", "grid": "#c9dbe2",
        "chart1": "#4f7a8a", "chart2": "#a9c4ce", "chart3": "#7fa8a0", "chart4": "#c98b6b", "chart5": "#d8e3e8",
    },
    "dark": {
        "bg": "#10202a", "sidebar": "#0b171e", "sidebar_hover": "#162a33",
        "sidebar_text": "#d9e8ee", "sidebar_muted": "#7f9ba6", "nav_active_text": "#e3eef2",
        "card": "#172c36", "input_bg": "#10232c", "border": "#24414d", "border_strong": "#33586a",
        "text": "#dfeaef", "heading": "#e8f2f5", "muted": "#8ea8b3", "hover": "#1e3843",
        "alt_row": "#1b323d", "selection": "#2b4d5b", "accent": "#5f9db1", "on_accent": "#0b171e",
        "tile_bg": "#1a3330", "tile_border": "#2a4d47", "icon_bg": "#224540", "icon_fg": "#86c9b4",
        "warn_bg": "#36251f", "warn_border": "#5a3a2d", "warn_icon_bg": "#4a2f25", "warn_fg": "#e39a77",
        "danger": "#ef8a7c", "grid": "#264350",
        "chart1": "#6fa3b5", "chart2": "#37596a", "chart3": "#7fb8a8", "chart4": "#d4936f", "chart5": "#2a4654",
    },
}

_current = "light"


def current_name() -> str:
    return _current


def color(token: str) -> QColor:
    return QColor(THEMES[_current][token])


def chart_colors() -> list[QColor]:
    return [color(f"chart{i}") for i in range(1, 6)]


_QSS = """
QWidget {{ color: {text}; }}
QMainWindow, QDialog, #Content, QScrollArea, #ScrollBody {{ background: {bg}; }}
QDialog {{ background: {card}; }}

#Sidebar {{ background: {sidebar}; }}
#Sidebar QLabel {{ color: {sidebar_text}; background: transparent; }}
#BrandName {{ font-weight: 600; font-size: 11pt; }}
#Sidebar #BrandSub {{ color: {sidebar_muted}; font-size: 8.5pt; }}
#Sidebar #Avatar {{ background: {sidebar_text}; color: {sidebar}; border: 3px solid {sidebar_muted};
    border-radius: 34px; font-size: 19pt; font-weight: 700; }}
QPushButton#NavButton {{ background: transparent; color: {sidebar_text}; border: none; text-align: left;
    padding: 10px 16px; border-top-left-radius: 19px; border-bottom-left-radius: 19px; font-size: 10pt; }}
QPushButton#NavButton:hover {{ background: {sidebar_hover}; }}
QPushButton#NavButton:checked {{ background: {bg}; color: {nav_active_text}; font-weight: 600; }}
#Sidebar #Version {{ color: {sidebar_muted}; font-size: 8pt; }}

#Header {{ background: {card}; border-bottom: 1px solid {border}; }}
#Welcome {{ font-size: 18pt; font-weight: 700; color: {heading}; }}
#Header #Hint {{ font-size: 9pt; }}
QLineEdit#HeaderSearch {{ border-radius: 17px; padding: 7px 14px; min-width: 260px; border: 1.5px solid {border_strong}; }}
QPushButton#ThemeToggle {{ background: {border_strong}; border: none; border-radius: 13px; padding: 0 4px;
    text-align: left; }}
QPushButton#ThemeToggle:checked {{ background: {accent}; text-align: right; }}
QToolButton#Bell {{ border: none; background: transparent; padding: 4px; color: {text}; font-weight: 600; }}
QToolButton#Bell[alert="true"] {{ color: {warn_fg}; }}
QToolButton#Bell:hover {{ background: {hover}; border-radius: 6px; }}

#Card {{ background: {card}; border: 1px solid {border}; border-radius: 10px; }}
#CardTitle {{ font-size: 11.5pt; font-weight: 600; color: {heading}; background: transparent; }}
#CardSub {{ color: {muted}; background: transparent; }}
#SectionHeading {{ font-size: 16pt; font-weight: 700; color: {heading}; padding: 2px 0 6px 0; }}
#Hint {{ color: {muted}; background: transparent; }}
#BigNumber {{ font-size: 20pt; font-weight: 700; color: {heading}; background: transparent; }}

#Tile {{ background: {tile_bg}; border: 1.5px solid {tile_border}; border-radius: 12px; }}
#Tile[tone="warn"] {{ background: {warn_bg}; border-color: {warn_border}; }}
#TileIcon {{ background: {icon_bg}; border-radius: 9px; }}
#TileIcon[tone="warn"] {{ background: {warn_icon_bg}; }}
#TileValue {{ font-size: 17pt; font-weight: 700; color: {heading}; background: transparent; }}
#TileCaption {{ color: {muted}; background: transparent; }}

QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {input_bg}; border: 1px solid {border_strong}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {accent}; selection-color: {on_accent}; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus {{ border: 1.5px solid {accent}; }}
QComboBox QAbstractItemView {{ background: {card}; selection-background-color: {selection};
    selection-color: {text}; border: 1px solid {border}; }}

QPushButton {{ background: {card}; border: 1px solid {border_strong}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {muted}; border-color: {border}; }}
QPushButton#Primary {{ background: {accent}; color: {on_accent}; border-color: {accent}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {heading}; border-color: {heading}; }}
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1.5px solid {border_strong}; border-radius: 4px;
    background: {input_bg}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({assets}/check.svg); }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ border: none; width: 24px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({assets}/chevron.svg); width: 12px; height: 12px; }}
QDateEdit {{ padding-right: 26px; }}
QDateEdit::drop-down {{ border: none; width: 24px; }}
QSpinBox, QDoubleSpinBox {{ padding-left: 8px; padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border: none; width: 20px; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({assets}/chevron-up.svg); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({assets}/chevron.svg); width: 10px; height: 10px; }}

QTableView {{ background: {card}; alternate-background-color: {alt_row}; border: 1px solid {border};
    border-radius: 10px; gridline-color: transparent; selection-background-color: {selection};
    selection-color: {text}; outline: 0; }}
QTableView::item {{ padding: 4px 6px; border: none; }}
QTableView::item:selected {{ background: {selection}; color: {text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {card}; color: {muted}; border: none; border-bottom: 1px solid {border};
    padding: 7px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: {card}; border: none; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 8px 18px; color: {muted}; border: none;
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {heading}; border-bottom: 2px solid {accent}; font-weight: 600; }}

QMenu {{ background: {card}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {selection}; color: {text}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border_strong}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border_strong}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QToolTip {{ background: {card}; color: {text}; border: 1px solid {border}; padding: 4px; }}
"""


def apply(app: QApplication, name: str) -> None:
    global _current
    _current = name if name in THEMES else "light"
    t = THEMES[_current]
    palette = QPalette()
    for role, token in (
        (QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "input_bg"), (QPalette.ColorRole.AlternateBase, "alt_row"),
        (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "card"),
        (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "on_accent"), (QPalette.ColorRole.ToolTipBase, "card"),
        (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.PlaceholderText, "muted"),
    ):
        palette.setColor(role, QColor(t[token]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t["muted"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t["muted"]))
    app.setPalette(palette)
    assets = resource_path("inventory_app/assets").as_posix()
    app.setStyleSheet(_QSS.format(assets=assets, **t))


# 24x24 stroke icons (drawn for this app).
_ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "box": '<path d="M3 7.5 12 3l9 4.5-9 4.5z"/><path d="M3 7.5v9L12 21l9-4.5v-9"/><path d="M12 12v9"/>',
    "movements": '<path d="M7 20V4"/><path d="m3 8 4-4 4 4"/><path d="M17 4v16"/><path d="m13 16 4 4 4-4"/>',
    "tag": '<path d="M3 12V4.5A1.5 1.5 0 0 1 4.5 3H12l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "truck": '<path d="M2 6h12v11H2z"/><path d="M14 10h4l4 4v3h-8"/><circle cx="6" cy="18" r="2"/>'
             '<circle cx="18" cy="18" r="2"/>',
    "reports": '<path d="M3 21h18"/><path d="M6 17v-6"/><path d="M11 17V7"/><path d="M16 17v-4"/><path d="M21 17V4"/>',
    "settings": '<path d="M4 6h9"/><path d="M17 6h3"/><circle cx="15" cy="6" r="2"/><path d="M4 12h3"/>'
                '<path d="M11 12h9"/><circle cx="9" cy="12" r="2"/><path d="M4 18h11"/><path d="M19 18h1"/>'
                '<circle cx="17" cy="18" r="2"/>',
    "data": '<ellipse cx="12" cy="5.5" rx="8" ry="2.5"/><path d="M4 5.5v13c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-13"/>'
            '<path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "trend": '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "alert": '<path d="M12 3 22 20H2z"/><path d="M12 10v4.5"/><path d="M12 17.5v.01"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.5-4.5"/>',
    "bell": '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
           'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
}


@lru_cache(maxsize=256)
def pixmap(name: str, hex_color: str, size: int = 20, ratio: float = 2.0) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{hex_color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, token: str = "text", checked_token: str | None = None, size: int = 20) -> QIcon:
    result = QIcon(pixmap(name, color(token).name(), size))
    if checked_token:
        result.addPixmap(pixmap(name, color(checked_token).name(), size), QIcon.Mode.Normal, QIcon.State.On)
    return result


def knob(dark: bool) -> QPixmap:
    """Round switch knob with a moon (light mode) or sun (dark mode) glyph."""
    ratio, size = 2.0, 18
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(0, 0, pm.width(), pm.height())
    glyph = pixmap("sun" if dark else "moon", "#2f5d6e", 14, ratio)
    p.drawPixmap(int(2 * ratio), int(2 * ratio), glyph)
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm
