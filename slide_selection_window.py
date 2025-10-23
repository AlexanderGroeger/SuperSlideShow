from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel, QGridLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import os, sys

class SlideSelectionWindow(QWidget):
    def __init__(self, slide_manager, presentation_window):
        super().__init__()
        self.slide_manager = slide_manager
        self.presentation_window = presentation_window
        self.setWindowTitle("Slide Selection")
        self.resize(800, 600)

        layout = QVBoxLayout()
        scroll = QScrollArea()
        container = QWidget()
        grid = QGridLayout(container)

        for i, slide in enumerate(self.slide_manager.slides):
            name_label = QLabel(slide["name"])
            name_label.setAlignment(Qt.AlignCenter)

            preview_path = slide["preview"]
            if preview_path and os.path.exists(preview_path):
                pixmap = QPixmap(preview_path).scaled(160, 90, Qt.KeepAspectRatio)
            else:
                pixmap = QPixmap(160, 90)
                pixmap.fill(Qt.darkGray)
            preview_label = QLabel()
            preview_label.setPixmap(pixmap)

            btn = QPushButton("Play")
            btn.clicked.connect(lambda checked, s=slide: self.open_slide(s))

            col, row = i % 4, i // 4
            grid.addWidget(preview_label, row * 3, col)
            grid.addWidget(name_label, row * 3 + 1, col)
            grid.addWidget(btn, row * 3 + 2, col)

        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        self.setLayout(layout)

    def open_slide(self, slide):
        self.presentation_window.load_slide(slide)
        self.presentation_window.showFullScreen()

    def closeEvent(self, event):
        """Ensure app quits when this window closes."""
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
