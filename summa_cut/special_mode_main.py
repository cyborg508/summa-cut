from PySide6.QtWidgets import QApplication

from .special_mode_window import SpecialModeWindow


def main() -> int:
    app = QApplication([])
    app.setApplicationName("summa-cut-special-mode")
    window = SpecialModeWindow()
    window.show()
    return app.exec()
