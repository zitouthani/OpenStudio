from __future__ import annotations

import csv
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from src.desktop.pipeline import CSV_READER, CSV_WRITER
from src.desktop.window import MainWindow


def test_desktop_window_runs_a_csv_job(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    input_path.write_text("name\nAlice\n", encoding="utf-8")

    window.add_component(CSV_READER)
    window._config_widgets[0].setText(str(input_path))
    window.add_component(CSV_WRITER)
    window._config_widgets[0].setText(str(output_path))
    window.run_job()

    with output_path.open(newline="", encoding="utf-8") as output_file:
        assert list(csv.DictReader(output_file)) == [{"name": "Alice"}]
    assert "Job completed: 1 row(s)." in window.statusBar().currentMessage()
    window.close()
    application.quit()
