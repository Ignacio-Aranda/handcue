import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from ..i18n import _
from . import icons
from . import theme as T


class Preview(QWidget):
    """Camera image with rounded corners and short toast messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = None
        self.placeholder_text = _("Opening the camera…")
        self.toast, self.toast_until, self.toast_error = "", 0.0, False
        self.setMinimumSize(480, 300)
        self.timer = QTimer(self, interval=250, timeout=self._expire_toast)
        self.timer.start()

    def _expire_toast(self):
        if self.toast and time.monotonic() > self.toast_until:
            self.toast = ""
            self.update()

    def show_frame(self, img):
        self.pixmap = QPixmap.fromImage(img)
        self.placeholder_text = ""
        self.update()

    def show_placeholder(self, text):
        self.pixmap, self.placeholder_text = None, text
        self.update()

    def show_toast(self, text, seconds=2.5, error=False):
        self.toast, self.toast_until, self.toast_error = text, time.monotonic() + seconds, error
        self.update()

    def _image_rect(self):
        m = T.S4
        avail = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        ratio = self.pixmap.width() / self.pixmap.height() if self.pixmap else 16 / 9
        w = min(avail.width(), avail.height() * ratio)
        h = w / ratio
        return QRectF(avail.center().x() - w / 2, avail.center().y() - h / 2, w, h)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self._image_rect()
        clip = QPainterPath()
        clip.addRoundedRect(r, T.RADIUS_LARGE, T.RADIUS_LARGE)
        p.setClipPath(clip)
        if self.pixmap:
            p.drawPixmap(r, self.pixmap, QRectF(self.pixmap.rect()))
        else:
            p.fillRect(r, QColor("#08090a"))
            icons.icon("webcam", T.TEXT_3).paint(p, int(r.center().x() - 20), int(r.center().y() - 44), 40, 40)
            p.setPen(QColor(T.TEXT_2))
            p.drawText(r.adjusted(0, 24, 0, 0), Qt.AlignmentFlag.AlignCenter, self.placeholder_text)
        p.setClipping(False)
        if self.toast:
            f = p.font()
            f.setPixelSize(13)
            f.setWeight(f.Weight.Medium)
            p.setFont(f)
            width = p.fontMetrics().horizontalAdvance(self.toast) + 2 * T.S4 + 24
            box = QRectF(r.center().x() - width / 2, r.bottom() - 52, width, 36)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(20, 21, 24, 235))
            p.drawRoundedRect(box, T.RADIUS, T.RADIUS)
            name, color = (("alert-circle-outline", T.DANGER) if self.toast_error
                           else ("check-circle-outline", T.SUCCESS))
            icons.icon(name, color).paint(p, int(box.left() + T.S3), int(box.center().y() - 8), 16, 16)
            p.setPen(QColor(T.TEXT))
            p.drawText(box.adjusted(T.S3 + 22, 0, -T.S3, 0), Qt.AlignmentFlag.AlignVCenter, self.toast)
