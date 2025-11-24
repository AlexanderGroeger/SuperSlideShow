from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtCore import QUrl, QSizeF, Signal, QObject
from PySide6.QtWidgets import QGraphicsPixmapItem
from PySide6.QtGui import QPixmap
from PySide6.QtSvgWidgets import QGraphicsSvgItem

class VideoLayer(QObject):
    video_ended = Signal()  # Signal emitted when video ends
    file_folder = "assets/video/"

    def __init__(self, spec: dict, scene, resize_callback):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        self.item = QGraphicsVideoItem()
        self.item.setPos(spec.get("x", 0), spec.get("y", 0))
        self.item.setZValue(spec.get("z", 0))
        self.item.setOpacity(spec.get("opacity", 1.0))

        self.loop = spec.get("loop", False)
        self.file = self.file_folder + spec["file"]
        self.resize_callback = resize_callback

        url = QUrl.fromLocalFile(self.file)
        self.player.setSource(url)
        self.player.setVideoOutput(self.item)

        # Handle auto-loop and end detection
        self.player.mediaStatusChanged.connect(self._handle_media_status)

        # Handle size updates
        self.player.videoOutputChanged.connect(lambda _: self._maybe_resize())
        self.player.playbackStateChanged.connect(lambda _: self._maybe_resize())
        self.player.metaDataChanged.connect(lambda _: self._maybe_resize())
        self.item.nativeSizeChanged.connect(lambda _: self.resize_callback(self))

        scene.addItem(self.item)

    def _maybe_resize(self):
        """Ask main window to resize this video layer based on the window size."""
        self.resize_callback(self)

    def _handle_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.video_ended.emit()  # Notify scene that video ended
            if self.loop:
                self.player.setPosition(0)
                self.player.play()

    def play(self):
        self.item.show()
        self.player.play()

    def stop(self):
        self.player.stop()
        self.item.hide()


class AudioTrack:

    file_folder = "assets/audio/"

    def __init__(self, spec: dict):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)  # max volume

        self.player.setAudioOutput(self.audio_output)

        url = QUrl.fromLocalFile(self.file_folder+spec["file"])
        self.player.setSource(url)

        self.loop = spec.get("loop", False)
        self.player.mediaStatusChanged.connect(self._handle_loop)

    def _handle_loop(self, status):
        if status == QMediaPlayer.EndOfMedia and self.loop:
            self.player.setPosition(0)
            self.player.play()

    def play(self):
        self.player.play()

    def stop(self):
        self.player.stop()


class OverlayLayer:

    file_folder = "assets/image/"

    def __init__(self, scene, spec):
        self.type = spec.get("type", "image")
        self.active_on_end = spec.get("active_on_end", False)
        self.visible = False

        self.pos = spec.get("position", [0, 0])
        self.size = spec.get("size", [50, 50])
        self.scene = scene

        if self.type == "arrow":
            self.item = QGraphicsSvgItem(self.file_folder+spec["file"])
        else:
            self.item = QGraphicsPixmapItem(QPixmap(self.file_folder+spec["file"]))

        self.item.setPos(*self.pos)
        self.item.setScale(1.0)
        self.item.setZValue(100)  # High z-value to appear on top
        self.item.setVisible(False)
        scene.addItem(self.item)

    def activate(self):
        self.item.setVisible(True)
        self.visible = True

    def deactivate(self):
        self.item.setVisible(False)
        self.visible = False

    def move_to(self, x, y):
        """Move overlay to a new position."""
        self.pos = [x, y]
        self.item.setPos(x, y)

    def move_by(self, dx, dy):
        """Move overlay by a relative amount."""
        self.pos[0] += dx
        self.pos[1] += dy
        self.item.setPos(*self.pos)