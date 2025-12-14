from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtCore import QUrl, QSizeF, Signal, QObject
from PySide6.QtWidgets import QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QTransform
from PySide6.QtSvgWidgets import QGraphicsSvgItem

class VideoLayer(QObject):
    video_ended = Signal()
    loop_completed = Signal()
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

        # Set all spec attributes FIRST
        self.delay = spec.get("delay", 0)
        self.loop = spec.get("loop", False)
        
        self.file = self.file_folder + spec["file"]
        self.resize_callback = resize_callback
        self.pending_transition = False

        url = QUrl.fromLocalFile(self.file)
        self.player.setSource(url)
        self.player.setVideoOutput(self.item)

        self.player.mediaStatusChanged.connect(self._handle_media_status)
        self.player.errorOccurred.connect(self._handle_error)
        self.player.videoOutputChanged.connect(lambda _: self._maybe_resize())
        self.player.metaDataChanged.connect(lambda _: self._maybe_resize())
        self.item.nativeSizeChanged.connect(lambda _: self.resize_callback(self))

        scene.addItem(self.item)

    def _maybe_resize(self):
        self.resize_callback(self)
    
    def _handle_error(self, error, error_string):
        print(f"VIDEO ERROR: {error} - {error_string}")
        print(f"Current file: {self.file}")
    
    def _handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.loop:
                self.loop_completed.emit()
                
                if self.pending_transition:
                    return
                
                self.player.setPosition(0)
                self.player.play()
            else:
                self.video_ended.emit()
    
    def request_transition(self):
        self.pending_transition = True
    
    def skip_to_end(self):
        duration = self.player.duration()
        if duration > 0:
            self.player.setPosition(duration - 100)

    def preload(self):
        self.item.show()
        self.player.pause()
    
    def play(self):
        self.item.show()
        self.pending_transition = False
        
        # CRITICAL: Reset position before playing to avoid showing last frame
        self.player.setPosition(0)
        
        if self.delay > 0:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(self.delay, self._delayed_play)
        else:
            self.player.play()
    
    def _delayed_play(self):
        self.player.play()

    def stop(self):
        self.player.stop()
        self.player.setPosition(0)  # Always reset to 0 when stopping
        self.item.hide()
        self.pending_transition = False
    
    def reset_and_reload(self):
        """Reset video position to 0."""
        self.player.stop()
        self.player.setPosition(0)


class AudioTrack:
    file_folder = "assets/audio/"

    def __init__(self, spec: dict):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)

        self.file = self.file_folder + spec["file"]
        url = QUrl.fromLocalFile(self.file)
        self.player.setSource(url)

        self.loop = spec.get("loop", False)
        self.delay = spec.get("delay", 0)
        self.start_position = spec.get("start", 0)  # Start position in milliseconds
        self.player.mediaStatusChanged.connect(self._handle_loop)
        
        # Track pending timer for cancellation
        self.pending_timer = None

    def _handle_loop(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.loop:
            self.player.setPosition(0)
            self.player.play()

    def play(self):
        # Cancel any previous pending timer
        if self.pending_timer:
            self.pending_timer.stop()
            self.pending_timer.deleteLater()
            self.pending_timer = None
        
        # Set start position if specified (only when first playing)
        if self.start_position > 0:
            self.player.setPosition(self.start_position)
        
        if self.delay > 0:
            from PySide6.QtCore import QTimer
            self.pending_timer = QTimer()
            self.pending_timer.setSingleShot(True)
            self.pending_timer.timeout.connect(self._delayed_play)
            self.pending_timer.start(self.delay)
        else:
            self.player.play()
    
    def _delayed_play(self):
        if self.pending_timer:
            self.pending_timer = None
        self.player.play()

    def stop(self):
        # CRITICAL: Aggressively stop and cancel everything
        if self.pending_timer:
            self.pending_timer.stop()
            try:
                self.pending_timer.timeout.disconnect()
            except:
                pass
            self.pending_timer.deleteLater()
            self.pending_timer = None
        
        self.player.stop()
        # Also pause to be extra sure
        self.player.pause()


class OverlayLayer:
    file_folder = "assets/image/"

    def __init__(self, scene, spec):
        self.type = spec.get("type", "image")
        self.active_on_end = spec.get("active_on_end", False)
        self.visible = False

        self.pos = spec.get("position", [0, 0])
        self.size = spec.get("size", [50, 50])
        self.scale_factor = spec.get("scale", 1.0)
        self.scene = scene

        if self.type == "arrow":
            self.item = QGraphicsSvgItem(self.file_folder+spec["file"])
        else:
            self.item = QGraphicsPixmapItem(QPixmap(self.file_folder+spec["file"]))

        self.item.setPos(*self.pos)
        self.item.setZValue(100)
        self.item.setVisible(False)
        
        transform = QTransform()
        transform.scale(self.scale_factor, self.scale_factor)
        self.item.setTransform(transform)
        
        print(f"[OverlayLayer] Created {self.type} at {self.pos} with scale {self.scale_factor}")
        
        scene.addItem(self.item)

    def activate(self):
        self.item.setVisible(True)
        self.visible = True

    def deactivate(self):
        self.item.setVisible(False)
        self.visible = False

    def move_to(self, x, y):
        self.pos = [x, y]
        self.item.setPos(x, y)

    def move_by(self, dx, dy):
        self.pos[0] += dx
        self.pos[1] += dy
        self.item.setPos(*self.pos)