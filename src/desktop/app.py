from __future__ import annotations


class OpenStudioApp:
    """Launcher for the optional PySide6 visual editor."""

    def __init__(self, title: str = "OpenStudio ETL") -> None:
        self.title = title

    def render(self) -> str:
        return f"{self.title} desktop editor."

    def run(self, argv: list[str] | None = None) -> int:
        """Start the desktop application, importing Qt only when requested."""
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError as error:
            raise RuntimeError(
                "The desktop editor requires PySide6. Install it with "
                "'python -m pip install -e \".[gui]\"'."
            ) from error

        from .window import MainWindow

        application = QApplication(argv or [])
        application.setApplicationName(self.title)
        window = MainWindow(self.title)
        window.show()
        return application.exec()


def main() -> int:
    """Entry point for the optional desktop editor."""
    return OpenStudioApp().run()


if __name__ == "__main__":
    raise SystemExit(main())
