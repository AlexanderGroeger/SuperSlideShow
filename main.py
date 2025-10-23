import sys
from PySide6.QtWidgets import QApplication
from slide_selection_window import SlideSelectionWindow
from presentation_window import PresentationWindow
from slide_manager import SlideManager

def main():
    app = QApplication(sys.argv)

    slide_manager = SlideManager("scenes")

    presentation_window = PresentationWindow(slide_manager)
    slide_selection_window = SlideSelectionWindow(slide_manager, presentation_window)

    # When the selection window closes, quit the app
    slide_selection_window.destroyed.connect(app.quit)

    slide_selection_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
