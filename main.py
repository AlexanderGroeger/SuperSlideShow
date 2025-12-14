import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QSizeF
from PySide6.QtGui import QBrush, QColor
from scene import SceneManager

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Layered Video Presentation")

        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.setCentralWidget(self.view)
        
        # Set black background
        self.scene.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        
        # Disable arrow key scrolling in the view
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # View doesn't capture focus

        # Load scenes from folder (starts with _default.yaml)
        self.manager = SceneManager("scenes", self.scene, self.resize_video_layer)

        self.setFocus()  # MainWindow gets focus, not the view

    def resizeEvent(self, event):
        """Handle window resize - scale all videos in current scene."""
        super().resizeEvent(event)
        if self.manager.current_scene:
            for vl in self.manager.current_scene.video_layers:
                self.resize_video_layer(vl)
            # Also resize static background if present
            self.manager._resize_static_background(self.manager.current_scene)
            # Update arrow position to match new video size/position
            # Use QTimer to ensure video position is updated first
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.manager.update_arrow_position)

    def resize_video_layer(self, vl):
        """Scale and center each video layer to fit the window while maintaining aspect ratio."""
        viewport_w = self.view.viewport().width()
        viewport_h = self.view.viewport().height()
        
        # Get the video's native size
        native_size = vl.item.nativeSize()
        if native_size.width() <= 0 or native_size.height() <= 0:
            # Video not loaded yet, use viewport size as fallback
            vl.item.setSize(QSizeF(viewport_w, viewport_h))
            vl.item.setPos(0, 0)
            return
        
        # Calculate aspect ratios
        viewport_aspect = viewport_w / viewport_h
        video_aspect = native_size.width() / native_size.height()
        
        # Calculate size to fit within viewport while maintaining aspect ratio
        if video_aspect > viewport_aspect:
            # Video is wider - fit to width
            new_w = viewport_w
            new_h = viewport_w / video_aspect
        else:
            # Video is taller - fit to height
            new_h = viewport_h
            new_w = viewport_h * video_aspect
        
        # Center the video
        x_offset = (viewport_w - new_w) / 2
        y_offset = (viewport_h - new_h) / 2
        
        vl.item.setSize(QSizeF(new_w, new_h))
        vl.item.setPos(x_offset, y_offset)

    def keyPressEvent(self, event):
        """Handle keyboard input for scene switching and arrow navigation."""
        # Arrow navigation
        if event.key() == Qt.Key.Key_Up:
            self.manager.move_arrow_up()
        elif event.key() == Qt.Key.Key_Down:
            self.manager.move_arrow_down()
        
        # Enter key - trigger "select" transition
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            next_scene = self.manager.get_transition("select")
            if next_scene:
                self.manager.switch_to(next_scene)
            # If next_scene is None, the transition was queued for later
        
        # Escape key - trigger "back" transition
        elif event.key() == Qt.Key.Key_Escape:
            back_scene = self.manager.get_transition("back")
            if back_scene:
                self.manager.switch_to(back_scene)
        
        # Number keys for direct scene access (optional)
        elif event.key() == Qt.Key.Key_1:
            self.manager.switch_to("question1")
        elif event.key() == Qt.Key.Key_2:
            self.manager.switch_to("question2")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1280, 720)
    window.show()
    sys.exit(app.exec())