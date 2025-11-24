import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QSizeF
from scene import SceneManager

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Layered Video Presentation")

        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.setCentralWidget(self.view)

        # Load scenes from folder (starts with _default.yaml)
        self.manager = SceneManager("scenes", self.scene, self.resize_video_layer)

        self.view.setFocus()

    def resizeEvent(self, event):
        """Handle window resize - scale all videos in current scene."""
        super().resizeEvent(event)
        if self.manager.current_scene:
            for vl in self.manager.current_scene.video_layers:
                self.resize_video_layer(vl)

    def resize_video_layer(self, vl):
        """Scale each video layer to fill the window."""
        w = self.view.viewport().width()
        h = self.view.viewport().height()
        vl.item.setSize(QSizeF(w, h))

    def keyPressEvent(self, event):
        """Handle keyboard input for scene switching and arrow navigation."""
        # Arrow navigation
        if event.key() == Qt.Key_Up:
            self.manager.move_arrow_up()
        elif event.key() == Qt.Key_Down:
            self.manager.move_arrow_down()
        
        # Enter key - trigger "select" transition
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            next_scene = self.manager.get_transition("select")
            if next_scene:
                self.manager.switch_to(next_scene)
        
        # Escape key - trigger "back" transition
        elif event.key() == Qt.Key_Escape:
            back_scene = self.manager.get_transition("back")
            if back_scene:
                self.manager.switch_to(back_scene)
        
        # Number keys for direct scene access (optional)
        elif event.key() == Qt.Key_1:
            self.manager.switch_to("question1")
        elif event.key() == Qt.Key_2:
            self.manager.switch_to("question2")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1280, 720)
    window.show()
    sys.exit(app.exec())