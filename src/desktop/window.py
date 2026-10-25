from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.engine.runtime import execute_graph
from src.job_model.job import Component, Job
from src.job_model.validation import validate_job

from .pipeline import (
    COMPONENT_LABELS,
    DEFAULT_CONFIGS,
    FILTER_OPERATORS,
    build_execution_graph,
    connect_in_order,
    create_component,
    validate_visual_job,
)


class PipelineCanvas(QGraphicsView):
    component_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#f3f6fa")))
        self.setMinimumWidth(420)
        self._selected_id: str | None = None
        self._components: list[Component] = []
        self._scene.selectionChanged.connect(self._selection_changed)

    def set_components(self, components: list[Component]) -> None:
        self._components = components
        component_ids = {component.id or component.name for component in components}
        if self._selected_id not in component_ids:
            self._selected_id = None
        self._draw_pipeline()

    def _draw_pipeline(self) -> None:
        self._scene.clear()
        self._scene.setSceneRect(0, 0, 560, max(320, len(self._components) * 112 + 32))

        for index in range(len(self._components) - 1):
            y = 48 + index * 112
            self._scene.addLine(280, y + 54, 280, y + 110, QPen(QColor("#94a3b8"), 2))

        for index, component in enumerate(self._components):
            component_id = component.id or component.name
            y = 24 + index * 112
            node = QGraphicsRectItem(100, y, 360, 56)
            node.setData(0, component_id)
            node.setBrush(QBrush(QColor("#e0edff" if component_id == self._selected_id else "#ffffff")))
            node.setPen(QPen(QColor("#2563eb" if component_id == self._selected_id else "#cbd5e1"), 2))
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self._scene.addItem(node)

            label = QGraphicsTextItem(
                f"{COMPONENT_LABELS.get(component.type, component.type)}  ·  {component.name}"
            )
            label.setDefaultTextColor(QColor("#172033"))
            label.setPos(116, y + 16)
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._scene.addItem(label)

    def _selection_changed(self) -> None:
        selected = self._scene.selectedItems()
        if not selected:
            return
        component_id = selected[0].data(0)
        if component_id:
            self._selected_id = str(component_id)
            self.component_selected.emit(self._selected_id)

    def select_component(self, component_id: str | None) -> None:
        self._selected_id = component_id
        self._draw_pipeline()

    @property
    def selected_id(self) -> str | None:
        return self._selected_id


class MainWindow(QMainWindow):
    def __init__(self, title: str = "OpenStudio ETL") -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1280, 820)
        self.job = Job(name="New ETL job")
        self.current_file: Path | None = None
        self._config_widgets: list[QWidget] = []

        self._build_menu()
        self._build_layout()
        self._apply_theme()
        self._refresh_canvas()
        self.statusBar().showMessage("Create a pipeline by adding a CSV Reader and CSV Writer.")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        save_action = QAction("&Save job", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_job)
        open_action = QAction("&Open job", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.load_job)
        file_menu.addAction(save_action)
        file_menu.addAction(open_action)

    def _build_layout(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("OpenStudio ETL")
        title.setObjectName("appTitle")
        subtitle = QLabel("Visual pipeline editor")
        subtitle.setObjectName("muted")
        heading = QVBoxLayout()
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch(1)
        header.addWidget(QLabel("Job name"))
        self.job_name = QLineEdit(self.job.name)
        self.job_name.setMaximumWidth(260)
        self.job_name.textChanged.connect(self._set_job_name)
        header.addWidget(self.job_name)

        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self.validate_current_job)
        self.run_button = QPushButton("Run job")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self.run_job)
        header.addWidget(self.validate_button)
        header.addWidget(self.run_button)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_palette())

        canvas_panel = QWidget()
        canvas_layout = QVBoxLayout(canvas_panel)
        canvas_layout.setContentsMargins(8, 0, 8, 0)
        canvas_heading = QLabel("PIPELINE")
        canvas_heading.setObjectName("sectionTitle")
        self.canvas = PipelineCanvas(self)
        self.canvas.component_selected.connect(self._show_component_properties)
        canvas_layout.addWidget(canvas_heading)
        canvas_layout.addWidget(self.canvas, 1)
        splitter.addWidget(canvas_panel)
        splitter.addWidget(self._build_properties())
        splitter.setSizes([210, 700, 300])
        layout.addWidget(splitter, 1)

        output_group = QGroupBox("Execution output")
        output_layout = QVBoxLayout(output_group)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText(
            "Run a valid pipeline to see a local preview of its output here."
        )
        self.output.setMaximumBlockCount(100)
        self.output.setMaximumHeight(170)
        output_layout.addWidget(self.output)
        layout.addWidget(output_group)

        self.setCentralWidget(root)

    def _build_palette(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        heading = QLabel("COMPONENTS")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Add a step to the pipeline:"))

        for component_type, label in COMPONENT_LABELS.items():
            button = QPushButton(f"+  {label}")
            button.setObjectName("paletteButton")
            button.clicked.connect(
                lambda checked=False, kind=component_type: self.add_component(kind)
            )
            layout.addWidget(button)

        layout.addStretch(1)
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.clicked.connect(self.remove_selected)
        layout.addWidget(self.remove_button)

        order_buttons = QHBoxLayout()
        move_up = QPushButton("Move up")
        move_up.clicked.connect(lambda: self.move_selected(-1))
        move_down = QPushButton("Move down")
        move_down.clicked.connect(lambda: self.move_selected(1))
        order_buttons.addWidget(move_up)
        order_buttons.addWidget(move_down)
        layout.addLayout(order_buttons)
        panel.setMinimumWidth(190)
        return panel

    def _build_properties(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(250)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        heading = QLabel("PROPERTIES")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        self.selected_label = QLabel("Select a component in the pipeline.")
        self.selected_label.setWordWrap(True)
        layout.addWidget(self.selected_label)
        self.properties_form = QFormLayout()
        self.properties_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        layout.addLayout(self.properties_form)
        layout.addStretch(1)
        return panel

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f8fafc; color: #172033; }
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QGraphicsView {
                background: #ffffff; border: 1px solid #d9e1ec; border-radius: 6px;
                padding: 7px;
            }
            QPushButton {
                background: #ffffff; border: 1px solid #d9e1ec; border-radius: 6px;
                padding: 8px 10px; text-align: left;
            }
            QPushButton:hover { border-color: #3b82f6; background: #eff6ff; }
            QPushButton#primaryButton { background: #2563eb; color: white; border: 0; }
            QPushButton#primaryButton:hover { background: #1d4ed8; }
            QPushButton#paletteButton { padding: 10px; }
            QGroupBox { border: 1px solid #d9e1ec; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
            QLabel#appTitle { font-size: 22px; font-weight: 700; }
            QLabel#sectionTitle { color: #64748b; font-size: 11px; font-weight: 700; }
            QLabel#muted { color: #64748b; }
            """
        )

    def _set_job_name(self, value: str) -> None:
        self.job.name = value

    def _refresh_canvas(self, selected_id: str | None = None) -> None:
        self.job.connections = connect_in_order(self.job.components)
        self.canvas.set_components(self.job.components)
        if selected_id:
            self.canvas.select_component(selected_id)
            self._show_component_properties(selected_id)

    def _find_component(self, component_id: str) -> Component | None:
        return next(
            (
                component
                for component in self.job.components
                if (component.id or component.name) == component_id
            ),
            None,
        )

    def add_component(self, component_type: str) -> None:
        self._save_active_properties()
        component = create_component(component_type)
        self.job.components.append(component)
        self._refresh_canvas(component.id)

    def remove_selected(self) -> None:
        selected = self.canvas.selected_id
        if selected is None:
            return
        self._save_active_properties()
        self.job.components = [
            component
            for component in self.job.components
            if (component.id or component.name) != selected
        ]
        self._clear_properties()
        self._refresh_canvas()

    def move_selected(self, offset: int) -> None:
        selected = self.canvas.selected_id
        if selected is None:
            return
        self._save_active_properties()
        index = next(
            (
                position
                for position, component in enumerate(self.job.components)
                if (component.id or component.name) == selected
            ),
            -1,
        )
        target = index + offset
        if index < 0 or target < 0 or target >= len(self.job.components):
            return
        self.job.components[index], self.job.components[target] = (
            self.job.components[target],
            self.job.components[index],
        )
        self._refresh_canvas(selected)

    def _clear_properties(self) -> None:
        while self.properties_form.rowCount():
            self.properties_form.removeRow(0)
        self._config_widgets.clear()
        self.selected_label.setText("Select a component in the pipeline.")

    def _show_component_properties(self, component_id: str) -> None:
        component = self._find_component(component_id)
        if component is None:
            return
        self._clear_properties()
        self.selected_label.setText(
            f"{COMPONENT_LABELS.get(component.type, component.type)}\n{component.name}"
        )
        for key, default in DEFAULT_CONFIGS[component.type].items():
            value = component.config.get(key, default)
            if key == "operator":
                editor = QComboBox()
                editor.addItems(FILTER_OPERATORS)
                editor.setCurrentText(str(value))
                editor.currentTextChanged.connect(
                    lambda new_value, item=component, field=key: item.config.__setitem__(
                        field, new_value
                    )
                )
            else:
                editor = QLineEdit(str(value))
                editor.setPlaceholderText(self._placeholder(component.type, key))
                editor.editingFinished.connect(
                    lambda field=key, widget=editor, item=component: item.config.__setitem__(
                        field, widget.text()
                    )
                )
            self.properties_form.addRow(key.replace("_", " ").title(), editor)
            self._config_widgets.append(editor)

    @staticmethod
    def _placeholder(component_type: str, key: str) -> str:
        examples = {
            ("csv_reader", "path"): "C:\\data\\input.csv",
            ("csv_reader", "delimiter"): ",",
            ("filter", "field"): "status",
            ("filter", "value"): "active",
            ("transform", "source_column"): "amount",
            ("transform", "target_column"): "amount_doubled",
            ("transform", "multiplier"): "2",
            ("csv_writer", "path"): "C:\\data\\output.csv",
        }
        return examples.get((component_type, key), "")

    def validate_current_job(self) -> None:
        self._save_active_properties()
        try:
            validate_visual_job(self.job)
        except ValueError as error:
            self.statusBar().showMessage(f"Validation failed: {error}", 8000)
            return
        self.statusBar().showMessage("Job is valid and ready to run.", 5000)

    def _save_active_properties(self) -> None:
        selected = self.canvas.selected_id
        if selected is None:
            return
        component = self._find_component(selected)
        if component is None:
            return
        for key, widget in zip(DEFAULT_CONFIGS[component.type], self._config_widgets):
            if isinstance(widget, QLineEdit):
                component.config[key] = widget.text()

    def save_job(self) -> None:
        if self.current_file is None:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save ETL job", "", "OpenStudio jobs (*.json)"
            )
            if not filename:
                return
            self.current_file = Path(filename)
        self._save_active_properties()
        try:
            self.current_file.write_text(
                json.dumps(self.job.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.critical(self, "Could not save job", str(error))
            return
        self.statusBar().showMessage(f"Saved {self.current_file}", 5000)

    def load_job(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open ETL job", "", "OpenStudio jobs (*.json)"
        )
        if not filename:
            return
        path = Path(filename)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("The job file must contain a JSON object.")
            loaded_job = Job.from_dict(payload)
            validate_job(loaded_job)
            for component in loaded_job.components:
                if component.type not in DEFAULT_CONFIGS:
                    raise ValueError(f"Unsupported component type: {component.type}")
                if not isinstance(component.config, dict):
                    raise TypeError(f"{component.name}: component config must be an object.")
            if loaded_job.connections != connect_in_order(loaded_job.components):
                raise ValueError("This editor only supports linear, ordered connections.")
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.critical(self, "Could not open job", str(error))
            return

        self.job = loaded_job
        self.current_file = path
        self.job_name.setText(self.job.name)
        self._clear_properties()
        self._refresh_canvas()
        self.output.clear()
        self.statusBar().showMessage(f"Opened {path}", 5000)

    def run_job(self) -> None:
        self._save_active_properties()
        try:
            graph = build_execution_graph(self.job)
            rows = execute_graph(graph, [])
        except (OSError, ValueError, TypeError) as error:
            self.output.clear()
            self.statusBar().showMessage(f"Execution failed: {error}", 10000)
            return

        preview = rows[:50]
        self.output.setPlainText(
            json.dumps(preview, indent=2, ensure_ascii=False, default=str)
            if preview
            else "The job completed successfully and produced no rows."
        )
        suffix = " (showing first 50)" if len(rows) > 50 else ""
        self.statusBar().showMessage(
            f"Job completed: {len(rows)} row(s){suffix}.", 8000
        )
