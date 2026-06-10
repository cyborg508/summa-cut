from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    app = QApplication([])
    app.setApplicationName("summa-cut")
    window = MainWindow()
    window.show()
    return app.exec()
