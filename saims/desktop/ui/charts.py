"""Lightweight charts drawn with QPainter so they follow the app theme."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from saims.desktop.ui import theme


def _compact(value: float) -> str:
    value = float(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= limit:
            return f"{value / limit:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,.0f}"


class _Chart(QWidget):
    empty_text = "No data yet"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def _painter(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return p

    def _draw_empty(self, p: QPainter) -> None:
        p.setPen(theme.color("muted"))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)

    @staticmethod
    def _font(p: QPainter, size: float, bold: bool = False) -> QFontMetrics:
        f = QFont(p.font())
        f.setPointSizeF(size)
        f.setBold(bold)
        p.setFont(f)
        return QFontMetrics(f)


class DonutChart(_Chart):
    """Ring chart with percentage labels and a legend on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[tuple[str, float]] = []
        self.setMinimumHeight(170)

    def set_data(self, items: list[tuple[str, float]], max_slices: int = 4) -> None:
        items = [(label, v) for label, v in items if v > 0]
        if len(items) > max_slices + 1:
            rest = sum(v for _, v in items[max_slices:])
            items = items[:max_slices] + [("Other", rest)]
        self.items = items
        self.update()

    def paintEvent(self, _event) -> None:
        p = self._painter()
        total = sum(v for _, v in self.items)
        if not total:
            self._draw_empty(p)
            return
        colors = theme.chart_colors()
        h = self.height()
        d = min(h - 16, self.width() * 0.45)
        ring = QRectF(12, (h - d) / 2, d, d)
        thickness = d * 0.30
        arc_rect = ring.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2)
        start = 90.0
        self._font(p, 8.5, bold=True)
        for i, (_, value) in enumerate(self.items):
            span = -360.0 * value / total
            pen = QPen(colors[i % len(colors)], thickness)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(arc_rect, int(start * 16), int(span * 16))
            share = value / total
            if share >= 0.06:
                mid = math.radians(start + span / 2)
                r = arc_rect.width() / 2
                c = arc_rect.center()
                pt = QPointF(c.x() + r * math.cos(mid), c.y() - r * math.sin(mid))
                slice_color = colors[i % len(colors)]
                p.setPen(QColor("#ffffff") if slice_color.lightness() < 150 else QColor("#1f3b47"))
                p.drawText(QRectF(pt.x() - 22, pt.y() - 9, 44, 18), Qt.AlignmentFlag.AlignCenter, f"{share:.0%}")
            start += span
        # legend
        fm = self._font(p, 9)
        x = ring.right() + 22
        line_h = 26
        y = h / 2 - line_h * len(self.items) / 2
        for i, (label, value) in enumerate(self.items):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colors[i % len(colors)])
            p.drawRoundedRect(QRectF(x, y + 5, 16, 16), 3, 3)
            p.setPen(theme.color("text"))
            text = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(self.width() - x - 30))
            p.drawText(QRectF(x + 24, y, self.width() - x - 24, line_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            y += line_h


class HBarChart(_Chart):
    """Ranked horizontal bars: label, bar, value."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[tuple[str, float]] = []
        self.formatter = _compact
        self.setMinimumHeight(220)

    def set_data(self, items: list[tuple[str, float]]) -> None:
        self.items = items
        self.update()

    def paintEvent(self, _event) -> None:
        p = self._painter()
        if not self.items:
            self._draw_empty(p)
            return
        fm = self._font(p, 8.5)
        top = max(v for _, v in self.items) or 1
        label_w = min(self.width() * 0.38, 150)
        value_w = 46
        row_h = min(28.0, self.height() / len(self.items))
        bar_h = min(12.0, row_h * 0.5)
        y = 4.0
        bar_x = label_w + 8
        max_bar = max(self.width() - bar_x - value_w - 4, 10)
        for label, value in self.items:
            p.setPen(theme.color("text"))
            p.drawText(QRectF(0, y, label_w, row_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(label, Qt.TextElideMode.ElideRight, int(label_w)))
            w = max(max_bar * value / top, 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("chart1"))
            p.drawRoundedRect(QRectF(bar_x, y + (row_h - bar_h) / 2, w, bar_h), 3, 3)
            p.setPen(theme.color("muted"))
            p.drawText(QRectF(bar_x + w + 6, y, value_w, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.formatter(value))
            y += row_h


class LineChart(_Chart):
    """Smoothed multi-series line chart. The first series is drawn filled; peaks get a tag."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels: list[str] = []
        self.series: list[tuple[str, list[float], str]] = []
        self.setMinimumHeight(200)

    def set_data(self, labels: list[str], series: list[tuple[str, list[float], str]]) -> None:
        """series: (name, values, colour token)."""
        self.labels, self.series = labels, series
        self.update()

    @staticmethod
    def _nice_max(value: float) -> tuple[float, float]:
        if value <= 0:
            return 4, 1
        raw = value / 4
        mag = 10 ** math.floor(math.log10(raw))
        step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
        return step * 4, step

    @staticmethod
    def _smooth(points: list[QPointF]) -> QPainterPath:
        path = QPainterPath(points[0])
        for i in range(len(points) - 1):
            p0 = points[i - 1] if i > 0 else points[i]
            p1, p2 = points[i], points[i + 1]
            p3 = points[i + 2] if i + 2 < len(points) else p2
            c1 = p1 + (p2 - p0) / 6
            c2 = p2 - (p3 - p1) / 6
            path.cubicTo(c1, c2, p2)
        return path

    def paintEvent(self, _event) -> None:
        p = self._painter()
        if not self.labels or not any(any(v) for _, v, _ in self.series):
            self._draw_empty(p)
            return
        fm = self._font(p, 8.5)
        top, step = self._nice_max(max(max(v) for _, v, _ in self.series))
        left, right, bottom, top_pad = fm.horizontalAdvance("0000k") + 10, 14, 26, 34
        plot = QRectF(left, top_pad, self.width() - left - right, self.height() - top_pad - bottom)

        # legend
        x = plot.right()
        for name, _, token in reversed(self.series):
            w = fm.horizontalAdvance(name)
            x -= w
            p.setPen(theme.color("muted"))
            p.drawText(QRectF(x, 4, w, 18), Qt.AlignmentFlag.AlignVCenter, name)
            x -= 16
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(token))
            p.drawEllipse(QRectF(x, 9, 9, 9))
            x -= 18

        # grid and axes
        grid_pen = QPen(theme.color("grid"), 1, Qt.PenStyle.DashLine)
        for i in range(5):
            y = plot.bottom() - plot.height() * i / 4
            p.setPen(grid_pen)
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(theme.color("muted"))
            p.drawText(QRectF(0, y - 9, left - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _compact(step * i))
        n = len(self.labels)
        xs = [plot.left() + (plot.width() * i / (n - 1) if n > 1 else plot.width() / 2) for i in range(n)]
        self._font(p, 8.5, bold=True)
        p.setPen(theme.color("text"))
        for x, label in zip(xs, self.labels):
            p.drawText(QRectF(x - 30, plot.bottom() + 6, 60, 18), Qt.AlignmentFlag.AlignCenter, label)

        # series
        for idx, (name, values, token) in enumerate(self.series):
            c = theme.color(token)
            points = [QPointF(x, plot.bottom() - plot.height() * v / top) for x, v in zip(xs, values)]
            path = self._smooth(points) if len(points) > 1 else QPainterPath(points[0])
            if idx == 0:
                area = QPainterPath(path)
                area.lineTo(points[-1].x(), plot.bottom())
                area.lineTo(points[0].x(), plot.bottom())
                area.closeSubpath()
                grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
                fill = QColor(c)
                fill.setAlpha(90)
                grad.setColorAt(0, fill)
                fill.setAlpha(10)
                grad.setColorAt(1, fill)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grad))
                p.drawPath(area)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(c, 2.2))
            p.drawPath(path)
            peak = max(range(len(values)), key=lambda i: values[i])
            if values[peak] > 0:
                self._tag(p, points[peak], f"Most {name.lower()}", c)

    def _tag(self, p: QPainter, pt: QPointF, text: str, c: QColor) -> None:
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.setBrush(c)
        p.drawEllipse(pt, 4.5, 4.5)
        fm = self._font(p, 7.5, bold=True)
        w = fm.horizontalAdvance(text) + 12
        x = min(max(pt.x() - w / 2, 0), self.width() - w)
        box = QRectF(x, pt.y() - 28, w, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
