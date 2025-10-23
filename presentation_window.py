from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QColor, QPalette

class PresentationWindow(QWidget):
    def __init__(self, slide_manager):
        super().__init__()
        self.slide_manager = slide_manager
        self.current_slide = None
        self.choices = []
        self.choice_index = 0

        self.setWindowTitle("Presentation")
        self.showFullScreen()

        # ----- Video / scene layer -----
        self.video_widget = QVideoWidget()
        self.video_widget.setContentsMargins(0, 0, 0, 0)

        # Make sure layout has no spacing or margins
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.layout.addWidget(self.video_widget)

        # ----- Transparent overlay for choices -----
        self.overlay = QWidget(self)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.overlay.setStyleSheet("background: transparent;")
        self.overlay_layout = QVBoxLayout(self.overlay)
        self.overlay_layout.setContentsMargins(0, 0, 0, 40)
        self.overlay_layout.setSpacing(10)
        self.overlay_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

        # ----- Media player -----
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setVideoOutput(self.video_widget)
        self.player.setAudioOutput(self.audio_output)

        # Add overlay to layout (on top of video)
        self.overlay.raise_()
        self.overlay.show()

    def resizeEvent(self, event):
        # Keep overlay covering the whole window
        self.overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def load_slide(self, slide):
        """Load a new scene with video and options."""
        self.current_slide = slide
        content = slide["content"]

        video_path = content.get("video")
        if video_path:
            self.player.setSource(video_path)
            self.player.play()

        self.choices = content.get("choices", [])
        self.choice_index = 0
        self.update_choice_display()

    def update_choice_display(self):
        # Clear existing widgets
        for i in reversed(range(self.overlay_layout.count())):
            item = self.overlay_layout.itemAt(i).widget()
            if item:
                item.setParent(None)

        # Add labels for each choice
        for i, choice in enumerate(self.choices):
            label = QLabel(choice["text"])
            label.setAlignment(Qt.AlignCenter)
            label.setFrameShape(QFrame.NoFrame)
            label.setStyleSheet(
                f"""
                color: white;
                background-color: rgba(0, 0, 0, {160 if i == self.choice_index else 90});
                border: 2px solid {'#ffffff' if i == self.choice_index else 'transparent'};
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 20px;
                """
            )
            self.overlay_layout.addWidget(label)

    def keyPressEvent(self, event):
        if not self.choices:
            return

        if event.key() in (Qt.Key_Up, Qt.Key_W):
            self.choice_index = (self.choice_index - 1) % len(self.choices)
        elif event.key() in (Qt.Key_Down, Qt.Key_S):
            self.choice_index = (self.choice_index + 1) % len(self.choices)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            selected = self.choices[self.choice_index]
            next_slide = self.slide_manager.get_slide_by_name(selected["next"])
            if next_slide:
                self.load_slide(next_slide)
        elif event.key() == Qt.Key_Escape:
            # Escape to close presentation
            self.close()
        self.update_choice_display()
