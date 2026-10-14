"""Small widgets built on the theme tokens."""
from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QObject, QPropertyAnimation, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QApplication, QButtonGroup,
    QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QScrollBar, QSizePolicy,
    QSlider,
    QToolButton, QVBoxLayout, QWidget,
)

from ..i18n import _
from . import icons
from . import theme as T


class WheelFilter(QObject):
    """The mouse wheel never changes sliders, combo boxes or spin boxes; it scrolls
    the panel that contains them instead."""

    TYPES = (QAbstractSlider, QComboBox, QAbstractSpinBox)

    def eventFilter(self, obj, ev):  # noqa: N802
        if ev.type() != QEvent.Type.Wheel or not isinstance(obj, self.TYPES) or isinstance(obj, QScrollBar):
            return False
        parent = obj.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            QApplication.sendEvent(parent.viewport(), ev)
        return True


def label(text, level=1, role=None, wrap=False):
    w = QLabel(text)
    # Always plain text: QLabel renders HTML by default, and these show names typed
    # by the user and values read from .desktop files.
    w.setTextFormat(Qt.TextFormat.PlainText)
    if level > 1:
        w.setProperty("level", str(level))
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


def ask(parent, title, text):
    """Yes/No confirmation that shows the text as is."""
    box = QMessageBox(QMessageBox.Icon.Question, title, text,
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    return box.exec() == QMessageBox.StandardButton.Yes


def show_error(parent, title, text):
    box = QMessageBox(QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok, parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.exec()


def scrollable(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(widget)
    return area


def separator():
    s = QFrame()
    s.setProperty("role", "separator")
    return s


def button(text, kind=None, icon=None):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if icon:
        color = "white" if kind == "primary" else T.DANGER if kind == "danger" else None
        b.setIcon(icons.icon(icon, color))
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def icon_button(icon, tooltip, checkable=False, checked=False, text=None, size=18):
    b = QToolButton()
    b.setIcon(icons.toggle_icon(icon) if checkable else icons.icon(icon))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setChecked(checked)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if text:
        b.setText(text)
        b.setProperty("withText", "true")
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    return b


def row(*widgets, spacing=T.S2):
    """Horizontal layout; None adds a stretch."""
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for w in widgets:
        if w is None:
            lay.addStretch()
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


class Dot(QWidget):
    def __init__(self, color=T.TEXT_3):
        super().__init__()
        self.color = color
        self.setFixedSize(8, 8)

    def set_color(self, color):
        self.color = color
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(0, 0, 8, 8)


class Switch(QAbstractButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._offset = 1.0 if checked else 0.0
        # Not called "pos": that is the widget position in Qt, and animating it moved
        # the whole switch across the window.
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, 20)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_quietly(self, on):
        """Changes the state without signals or animation."""
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._offset = 1.0 if on else 0.0
        self.update()

    def _get_offset(self):
        return self._offset

    def _set_offset(self, v):
        self._offset = v
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on, off = QColor(T.ACCENT), QColor(T.BORDER_STRONG)
        k = self._offset
        c = QColor(int(off.red() + (on.red() - off.red()) * k), int(off.green() + (on.green() - off.green()) * k),
                   int(off.blue() + (on.blue() - off.blue()) * k))
        if not self.isEnabled():
            c.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(0, 0, 34, 20), 10, 10)
        p.setBrush(QColor(255, 255, 255, 255 if self.isEnabled() else 150))
        p.drawEllipse(QRectF(2 + k * 14, 2, 16, 16))


class Section(QWidget):
    """Collapsible group: small uppercase header plus content."""

    def __init__(self, title, expanded=True, extra=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.S4, T.S3, T.S4, T.S4)
        lay.setSpacing(T.S3)
        header = QHBoxLayout()
        header.setSpacing(T.S1)
        self.header = QPushButton()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 0; min-height: 24px; }")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(T.S1)
        self.chevron = QLabel()
        hl.addWidget(self.chevron)
        hl.addWidget(label(title.upper(), role="heading"))
        hl.addStretch()
        self.header.clicked.connect(lambda: self.set_expanded(not self.body.isVisible()))
        header.addWidget(self.header, 1)
        if extra is not None:
            header.addWidget(extra)
        lay.addLayout(header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(T.S4)
        lay.addWidget(self.body)
        self.set_expanded(expanded)

    def set_expanded(self, on):
        self.body.setVisible(on)
        self.chevron.setPixmap(icons.icon("chevron-down" if on else "chevron-right", T.TEXT_3).pixmap(16, 16))

    def add(self, w):
        if isinstance(w, QWidget):
            self.body_layout.addWidget(w)
        else:
            self.body_layout.addLayout(w)
        return w


class Inspector(QWidget):
    """Column of sections separated by thin lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)

    def add(self, w):
        if self.lay.count():
            self.lay.addWidget(separator())
        self.lay.addWidget(w)
        return w

    def clear(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def finish(self):
        self.lay.addStretch()


class SettingRow(QWidget):
    """Title (and optional help text) on the left, control on the right."""

    def __init__(self, title, control, help_text="", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(T.S3)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = label(title)
        col.addWidget(self.title)
        if help_text:
            self.help = label(help_text, level=2, wrap=True)
            col.addWidget(self.help)
        lay.addLayout(col, 1)
        lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.control = control


class SwitchRow(SettingRow):
    def __init__(self, title, checked=False, help_text="", parent=None):
        self.switch = Switch(checked)
        super().__init__(title, self.switch, help_text, parent)
        self.toggled = self.switch.toggled

    def isChecked(self):  # noqa: N802
        return self.switch.isChecked()

    def setChecked(self, on):  # noqa: N802
        self.switch.set_quietly(on)


class SliderRow(QWidget):
    """Title, value on the right and a slider underneath. Double-click the title to
    reset to the default value."""
    changed = Signal(int)

    def __init__(self, title, minimum, maximum, value, default=None, fmt=str, step=1, parent=None):
        super().__init__(parent)
        self.fmt, self.default, self.minimum, self.step = fmt, default, minimum, max(1, step)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(T.S1)
        self.title = label(title)
        if default is not None:
            self.title.setToolTip(_("Double-click to reset"))
        self.value_label = label("", role="value")
        lay.addLayout(row(self.title, None, self.value_label))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, (maximum - minimum) // self.step)
        self.slider.setValue((value - minimum) // self.step)
        self.slider.valueChanged.connect(self._on_change)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.slider)
        self.lay = lay
        self._update_text()
        self.title.mouseDoubleClickEvent = lambda _event: self.reset()

    def _on_change(self, _pos):
        self._update_text()
        self.changed.emit(self.value())

    def _update_text(self):
        self.value_label.setText(self.fmt(self.value()))

    def value(self):
        return self.minimum + self.slider.value() * self.step

    def setValue(self, v, emit=False):  # noqa: N802
        self.slider.blockSignals(not emit)
        self.slider.setValue(round((v - self.minimum) / self.step))
        self.slider.blockSignals(False)
        self._update_text()

    def reset(self):
        if self.default is not None and self.isEnabled():
            self.setValue(self.default, emit=True)


class Segmented(QFrame):
    """Mutually exclusive options on a shared background."""
    changed = Signal(object)

    def __init__(self, options, current=None, icon_names=None, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        self.setStyleSheet(f"""
            QFrame#segmented {{ background: {T.RAISED}; border: 1px solid {T.BORDER}; border-radius: {T.RADIUS}px; }}
            QFrame#segmented QPushButton {{ background: transparent; border: none; border-radius: 4px;
                color: {T.TEXT_2}; min-height: 26px; padding: 0 {T.S2}px; font-weight: 500; }}
            QFrame#segmented QPushButton:hover {{ color: {T.TEXT}; }}
            QFrame#segmented QPushButton:checked {{ background: {T.PRESSED}; color: {T.TEXT}; }}
            QFrame#segmented QPushButton:disabled {{ color: {T.TEXT_3}; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.values = []
        for i, (value, text) in enumerate(options):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if icon_names:
                b.setIcon(icons.toggle_icon(icon_names[i]))
                b.setIconSize(QSize(16, 16))
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.values.append(value)
        self.set(current if current in self.values else self.values[0])
        self.group.idClicked.connect(lambda i: self.changed.emit(self.values[i]))

    def set(self, value):
        if value in self.values:
            self.group.button(self.values.index(value)).setChecked(True)

    def value(self):
        return self.values[self.group.checkedId()]


class TemperatureBar(QWidget):
    """Warm-to-cool gradient under the color temperature slider."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QColor("#ff9d4d"))
        g.setColorAt(0.5, QColor("#f4efe6"))
        g.setColorAt(1, QColor("#7fa8ff"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(7, 0, self.width() - 14, 4), 2, 2)


class FramingMap(QWidget):
    """Digital framing: the rectangle is the part of the sensor visible at the current
    zoom, and dragging it moves the framing. Coordinates as shown in the preview."""
    moved = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(132)
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set(self, zoom, cx, cy):
        self.zoom, self.cx, self.cy = zoom, cx, cy
        self.update()

    def _area(self):
        w = min(self.width() - 2, (self.height() - 2) * 16 / 9)
        h = w * 9 / 16
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        a = self._area()
        p.setPen(QPen(QColor(T.BORDER_STRONG), 1))
        p.setBrush(QColor(T.BG))
        p.drawRoundedRect(a, T.RADIUS, T.RADIUS)
        p.setPen(QPen(QColor(T.BORDER), 1, Qt.PenStyle.DashLine))
        for k in (1, 2):
            x = int(a.left() + a.width() * k / 3)
            p.drawLine(x, int(a.top() + 4), x, int(a.bottom() - 4))
            y = int(a.top() + a.height() * k / 3)
            p.drawLine(int(a.left() + 4), y, int(a.right() - 4), y)
        w, h = a.width() / self.zoom, a.height() / self.zoom
        r = QRectF(a.left() + self.cx * a.width() - w / 2, a.top() + self.cy * a.height() - h / 2, w, h)
        r = r.adjusted(1, 1, -1, -1)
        accent = QColor(T.ACCENT if self.isEnabled() else T.TEXT_3)
        fill = QColor(accent)
        fill.setAlpha(36)
        p.setPen(QPen(accent, 1.5))
        p.setBrush(fill)
        p.drawRoundedRect(r, 4, 4)
        f = p.font()
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(T.TEXT_2))
        p.drawText(a.adjusted(T.S2, T.S1, -T.S2, -T.S1), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                   f"{self.zoom:.1f}×")

    def _move_to(self, pos):
        if self.zoom <= 1.0 or not self.isEnabled():
            return
        a = self._area()
        m = 0.5 / self.zoom
        self.cx = min(1 - m, max(m, (pos.x() - a.left()) / a.width()))
        self.cy = min(1 - m, max(m, (pos.y() - a.top()) / a.height()))
        self.update()
        self.moved.emit(self.cx, self.cy)

    def mousePressEvent(self, e):  # noqa: N802
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._move_to(e.position())

    def mouseMoveEvent(self, e):  # noqa: N802
        self._move_to(e.position())

    def mouseReleaseEvent(self, _event):  # noqa: N802
        self.setCursor(Qt.CursorShape.OpenHandCursor)
