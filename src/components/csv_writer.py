from __future__ import annotations

import csv
import os
import re
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

from src.component_sdk.contracts import ComponentContract


class CSVWriter(ComponentContract):
    """Write rows to disk as CSV files."""

    def __init__(self, path: str) -> None:
        self.path = path

    def process(self, rows: Iterable[dict]) -> list[dict]:
        row_list = list(rows)
        if not row_list:
            return []

        fieldnames = list(row_list[0].keys())
        with open(self.path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(row_list)
        return row_list

    def begin_batches(self, resume: bool) -> None:
        if not resume:
            shutil.rmtree(self._batch_dir, ignore_errors=True)
            shutil.rmtree(self._completed_dir, ignore_errors=True)

    def process_batch(self, rows: Iterable[dict], batch_id: str) -> list[dict]:
        row_list = list(rows)
        if not row_list:
            return []

        self._batch_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", batch_id)
        batch_path = self._batch_dir / f"{safe_id}.csv"
        temporary_path = self._write_temporary(batch_path.parent, batch_path.name, row_list)
        try:
            os.replace(temporary_path, batch_path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise
        return row_list

    def finalize_batches(self) -> None:
        batch_paths = sorted(self._batch_dir.glob("*.csv"))
        if not batch_paths:
            return

        first_reader = None
        fieldnames = None
        for batch_path in batch_paths:
            with batch_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames:
                    fieldnames = reader.fieldnames
                    first_reader = batch_path
                    break
        if fieldnames is None or first_reader is None:
            return

        destination = Path(self.path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                for batch_path in batch_paths:
                    with batch_path.open(newline="", encoding="utf-8") as source:
                        reader = csv.DictReader(source)
                        writer.writerows(reader)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, destination)
            os.replace(self._batch_dir, self._completed_dir)
            shutil.rmtree(self._completed_dir)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def rollback_batch(self, batch_id: str) -> None:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", batch_id)
        (self._batch_dir / f"{safe_id}.csv").unlink(missing_ok=True)
        try:
            self._batch_dir.rmdir()
        except OSError:
            pass

    @property
    def _batch_dir(self) -> Path:
        return Path(f"{self.path}.batches")

    @property
    def _completed_dir(self) -> Path:
        return Path(f"{self._batch_dir}.complete")

    @staticmethod
    def _write_temporary(directory: Path, name: str, rows: list[dict]) -> str:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{name}.",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                os.fsync(handle.fileno())
            return temporary_name
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
