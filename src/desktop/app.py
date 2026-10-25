from __future__ import annotations


class OpenStudioApp:
    """Application shell for the future desktop interface."""

    def __init__(self, title: str = "OpenStudio ETL") -> None:
        self.title = title

    def render(self) -> str:
        return f"{self.title} ready for the visual editor."
