"""Light and dark colour themes, the application stylesheet and line icons."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QIconEngine, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from saims.paths import resource_path

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#d3e5ec", "sidebar": "#2f5d6e", "sidebar_hover": "#386878",
        "sidebar_text": "#e8f1f4", "sidebar_muted": "#a9c3cc", "nav_active_bg": "#e3eff3", "nav_active_text": "#24505f",
        "card": "#f5fafc", "input_bg": "#ffffff", "border": "#c5dae2", "border_strong": "#9fbcc7",
        "text": "#1f3b47", "heading": "#1f4a5a", "muted": "#5e7a86", "hover": "#e4f0f4",
        "alt_row": "#edf5f8", "selection": "#c4dde6", "accent": "#3f6f80", "on_accent": "#ffffff",
        "tile_bg": "#f2f8f6", "tile_border": "#c3dcd4", "icon_bg": "#cfe8df", "icon_fg": "#3d7a68",
        "warn_bg": "#fbefe9", "warn_border": "#e7c2b0", "warn_icon_bg": "#f6d9cb", "warn_fg": "#b5643f",
        "danger": "#c0392b", "grid": "#c9dbe2", "ok": "#2e7d5b", "info": "#2f6fa8", "warning": "#b26a12",
        "chart1": "#4f7a8a", "chart2": "#a9c4ce", "chart3": "#7fa8a0", "chart4": "#c98b6b", "chart5": "#d8e3e8", "chart6": "#a05f6e",
    },
    "dark": {
        "bg": "#10202a", "sidebar": "#0b171e", "sidebar_hover": "#13252d",
        "sidebar_text": "#d9e8ee", "sidebar_muted": "#7f9ba6", "nav_active_bg": "#1f3d49", "nav_active_text": "#f1f8fa",
        "card": "#172c36", "input_bg": "#10232c", "border": "#24414d", "border_strong": "#33586a",
        "text": "#dfeaef", "heading": "#e8f2f5", "muted": "#8ea8b3", "hover": "#1e3843",
        "alt_row": "#1b323d", "selection": "#2b4d5b", "accent": "#5f9db1", "on_accent": "#0b171e",
        "tile_bg": "#1a3330", "tile_border": "#2a4d47", "icon_bg": "#224540", "icon_fg": "#86c9b4",
        "warn_bg": "#36251f", "warn_border": "#5a3a2d", "warn_icon_bg": "#4a2f25", "warn_fg": "#e39a77",
        "danger": "#ef8a7c", "grid": "#264350", "ok": "#6cc79b", "info": "#79b0e0", "warning": "#e0b25c",
        "chart1": "#6fa3b5", "chart2": "#37596a", "chart3": "#7fb8a8", "chart4": "#d4936f", "chart5": "#2a4654", "chart6": "#c58796",
    },
}

_current = "light"


def current_name() -> str:
    return _current


def color(token: str) -> QColor:
    return QColor(THEMES[_current][token])


def chart_colors() -> list[QColor]:
    return [color(f"chart{i}") for i in range(1, 7)]


_QSS = """
QWidget {{ color: {text}; }}
QMainWindow, QDialog, #Content, QScrollArea, #ScrollBody {{ background: {bg}; }}
QDialog {{ background: {card}; }}

#Sidebar {{ background: {sidebar}; }}
#Sidebar QLabel {{ color: {sidebar_text}; background: transparent; }}
#BrandName {{ font-weight: 600; font-size: 11pt; }}
#Sidebar #BrandSub {{ color: {sidebar_muted}; font-size: 8.5pt; }}
#SchoolBlock #BrandName {{ font-size: 9.5pt; font-weight: 600; }}
#Sidebar #Avatar {{ background: {sidebar_text}; color: {sidebar}; border: 2px solid {sidebar_muted};
    border-radius: 20px; font-size: 11pt; font-weight: 700; }}
#SchoolBlock {{ background: {sidebar_hover}; border-radius: 12px; }}
#SchoolBlock QLabel {{ background: transparent; }}
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
QToolButton#UserMenu {{ border: none; background: transparent; padding: 4px 6px; color: {text}; font-weight: 600; }}
QToolButton#UserMenu:hover {{ background: {hover}; border-radius: 6px; }}
QToolButton#UserMenu::menu-indicator {{ image: none; width: 0; }}

#Card {{ background: {card}; border: 1px solid {border}; border-radius: 10px; }}
#CardTitle {{ font-size: 11.5pt; font-weight: 600; color: {heading}; background: transparent; }}
#CardSub {{ color: {muted}; background: transparent; }}
#SectionHeading {{ font-size: 16pt; font-weight: 700; color: {heading}; padding: 2px 0 6px 0; }}
#Hint {{ color: {muted}; background: transparent; }}
#FormError {{ color: {danger}; background: {warn_bg}; border: 1px solid {warn_border}; border-radius: 6px;
    padding: 8px 10px; }}
#RoleChip {{ color: {accent}; background: {tile_bg}; border: 1px solid {tile_border}; border-radius: 10px;
    padding: 2px 10px; font-size: 8.5pt; font-weight: 600; }}
#DetailTitle {{ font-size: 14pt; font-weight: 700; color: {heading}; background: transparent; }}
#DetailKey {{ color: {muted}; background: transparent; }}
#StatusPill {{ border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 9pt; }}
#Toolbar QPushButton {{ padding: 6px 12px; }}
QListWidget#ReportList {{ background: {card}; border: 1px solid {border}; border-radius: 10px; padding: 6px; outline: 0; }}
QListWidget#ReportList::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget#ReportList::item:selected {{ background: {selection}; color: {text}; }}
QListWidget#History {{ background: transparent; border: none; outline: 0; }}
QListWidget#History::item {{ padding: 6px 2px; border-bottom: 1px solid {border}; }}
QListWidget#History::item:selected {{ background: transparent; color: {text}; }}
QPushButton#Link {{ border: none; background: transparent; color: {accent}; text-align: left; padding: 2px 0; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
#LoginBrand {{ background: {sidebar}; }}
#LoginBrand QLabel {{ color: {sidebar_text}; background: transparent; }}
#LoginTitle {{ font-size: 24pt; font-weight: 800; }}
#LoginPanel {{ background: {card}; }}
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
    assets = resource_path("saims/assets").as_posix()
    app.setStyleSheet(_QSS.format(assets=assets, **t))


# Line icons on a 24x24 grid with one stroke weight (drawn for this app). They are rendered as vectors at the
# exact size and display scale Qt asks for, so they stay sharp at 100%, 125%, 150% and 200% scaling.
_ICONS = {
    "dashboard": '<rect x="3" y="3" width="7.5" height="9" rx="2"/><rect x="13.5" y="3" width="7.5" height="5" rx="2"/>'
                 '<rect x="13.5" y="11" width="7.5" height="10" rx="2"/><rect x="3" y="15" width="7.5" height="6" rx="2"/>',
    "box": '<path d="M12 2.8 20.5 7.4v9.2L12 21.2l-8.5-4.6V7.4z"/><path d="m3.8 7.6 8.2 4.5 8.2-4.5"/>'
           '<path d="M12 12.1v9"/><path d="m7.8 5.1 8.4 4.7"/>',
    "layers": '<path d="m12 2.6 9 4.7-9 4.7-9-4.7z"/><path d="m3 12 9 4.7 9-4.7"/><path d="m3 16.6 9 4.7 9-4.7"/>',
    "swap": '<path d="M4 8h15"/><path d="m15 4 4 4-4 4"/><path d="M20 16H5"/><path d="m9 12-4 4 4 4"/>',
    "people": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20.5c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/>'
              '<path d="M16 4.7a3.5 3.5 0 0 1 0 6.6"/><path d="M18 14.8c2.1.6 3.5 2.6 3.5 5.7"/>',
    "school": '<path d="M2.5 21h19"/><path d="M4.5 21v-10L12 5.5l7.5 5.5v10"/><path d="M10 21v-4.5h4V21"/>'
              '<circle cx="12" cy="11.5" r="1.8"/><path d="M12 5.5V2.2h3.2v2.2H12"/>',
    "reports": '<path d="M3.5 3.5v15a2 2 0 0 0 2 2h15"/><path d="M8.5 16.5v-4"/><path d="M13 16.5v-9"/>'
               '<path d="M17.5 16.5v-6"/>',
    "history": '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.5"/><path d="M3.5 4v4.5H8"/><path d="M12 7.5V12l3 2"/>',
    "shield": '<path d="M12 2.8 19.5 5.6v6c0 4.6-3.1 8-7.5 9.6-4.4-1.6-7.5-5-7.5-9.6v-6z"/>'
              '<path d="m8.8 12 2.2 2.2 4.4-4.4"/>',
    "settings": '<path d="M10.40 4.57 L10.67 2.09 L13.33 2.09 L13.60 4.57 L16.12 5.62 L18.07 4.05 L19.95 5.93 '
                'L18.38 7.88 L19.43 10.40 L21.91 10.67 L21.91 13.33 L19.43 13.60 L18.38 16.12 L19.95 18.07 '
                'L18.07 19.95 L16.12 18.38 L13.60 19.43 L13.33 21.91 L10.67 21.91 L10.40 19.43 L7.88 18.38 '
                'L5.93 19.95 L4.05 18.07 L5.62 16.12 L4.57 13.60 L2.09 13.33 L2.09 10.67 L4.57 10.40 L5.62 7.88 '
                'L4.05 5.93 L5.93 4.05 L7.88 5.62Z"/><circle cx="12" cy="12" r="3"/>',
    "logout": '<path d="M9 21H5.5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2H9"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "clipboard": '<rect x="4.5" y="4" width="15" height="17.5" rx="2"/><path d="M9 4V2.5h6V4"/>'
                 '<path d="m9 13 2 2 4-4"/>',
    "movements": '<path d="M7 20V4"/><path d="m3 8 4-4 4 4"/><path d="M17 4v16"/><path d="m13 16 4 4 4-4"/>',
    "tag": '<path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "truck": '<path d="M2.5 5.5h11.5v11.5H2.5z"/><path d="M14 9.5h4l3.5 4v3.5H14"/><circle cx="6.5" cy="18" r="2"/>'
             '<circle cx="17.5" cy="18" r="2"/>',
    "data": '<ellipse cx="12" cy="5.5" rx="8" ry="2.5"/><path d="M4 5.5v13c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-13"/>'
            '<path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/>',
    "trend": '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "alert": '<path d="M10.3 3.9 2.4 17.6a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
             '<path d="M12 9.5v4"/><path d="M12 17h.01"/>',
    "qr": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
          '<rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/>',
    "file": '<path d="M6 2.5h8l5 5V20a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 20V4a1.5 1.5 0 0 1 1-1.5z"/>'
            '<path d="M14 2.5V8h5"/><path d="M9 13h6M9 17h6"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9"/><path d="m16 7 3 3"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.5-4.5"/>',
    "bell": '<path d="M6 8.5a6 6 0 0 1 12 0c0 6 2.5 8 2.5 8h-17S6 14.5 6 8.5"/><path d="M10.3 20a2 2 0 0 0 3.4 0"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
           'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
}
STROKE = 1.9


@lru_cache(maxsize=512)
def _renderer(name: str, hex_color: str, stroke: float = STROKE) -> QSvgRenderer:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{hex_color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')
    return QSvgRenderer(QByteArray(svg.encode()))


def paint_icon(painter: QPainter, name: str, hex_color: str, rect: QRectF) -> None:
    """Draw an icon as vectors straight onto a painter (used by custom-painted widgets)."""
    _renderer(name, hex_color).render(painter, rect)


def _screen_ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen else 2.0


def pixmap(name: str, hex_color: str, size: int = 20, ratio: float | None = None) -> QPixmap:
    """Icon pixmap rendered at the display's scale (for QLabel and other pixmap-only places)."""
    return _pixmap(name, hex_color, size, ratio or _screen_ratio())


@lru_cache(maxsize=256)
def _pixmap(name: str, hex_color: str, size: int, ratio: float) -> QPixmap:
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _renderer(name, hex_color).render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


class _IconEngine(QIconEngine):
    """Renders an SVG icon at whatever size and scale a widget asks for, so QIcons never get resampled."""

    def __init__(self, name: str, normal: str, checked: str | None, disabled: str):
        super().__init__()
        self.name, self.normal, self.checked, self.disabled = name, normal, checked, disabled

    def _color(self, mode, state) -> str:
        if mode == QIcon.Mode.Disabled:
            return self.disabled
        if state == QIcon.State.On and self.checked:
            return self.checked
        return self.normal

    def paint(self, painter, rect, mode, state):
        paint_icon(painter, self.name, self._color(mode, state), QRectF(rect))

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size, mode, state, scale):
        side = min(size.width(), size.height())
        return _pixmap(self.name, self._color(mode, state), side, scale)

    def actualSize(self, size, mode, state):
        side = min(size.width(), size.height())
        return QSize(side, side)

    def clone(self):
        return _IconEngine(self.name, self.normal, self.checked, self.disabled)


def icon(name: str, token: str = "text", checked_token: str | None = None, size: int = 20) -> QIcon:
    """Theme-coloured icon. `size` is kept for callers; the engine renders at the size the widget uses."""
    return QIcon(_IconEngine(name, color(token).name(), color(checked_token).name() if checked_token else None,
                             color("muted").name()))


@lru_cache(maxsize=32)
def _svg_asset(rel: str, width: int, ratio: float) -> QPixmap:
    renderer = QSvgRenderer(str(resource_path(rel)))
    size = renderer.defaultSize()
    height = round(width * size.height() / max(size.width(), 1))
    pm = QPixmap(round(width * ratio), round(height * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def logo(width: int, reverse: bool = False) -> QPixmap:
    """The SAIMS logo (box + wordmark) at `width` logical pixels, sharp at the screen's scale.

    `reverse` is the version for teal or dark backgrounds (the sidebar, the sign-in panel)."""
    return _svg_asset(f"saims/assets/logo{'-inverse' if reverse else ''}.svg", width, _screen_ratio())


def logo_image(width_px: int) -> QImage:
    """Full-colour logo as an image for documents (PDF exports)."""
    return _svg_asset("saims/assets/logo.svg", width_px, 1.0).toImage()


def knob(dark: bool) -> QPixmap:
    """Round switch knob with a moon (light mode) or sun (dark mode) glyph."""
    ratio, size = max(_screen_ratio(), 1.0), 18
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
