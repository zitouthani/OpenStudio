from __future__ import annotations

from typing import Any

from .job import Job


def validate_job(job: Job) -> None:
    """Validate the minimum rules for a runnable ETL job."""
    if not job.name.strip():
        raise ValueError("Job name is required.")
    if not job.components:
        raise ValueError("At least one component is required.")

    ids = []
    for component in job.components:
        if not component.name.strip():
            raise ValueError("Each component requires a non-empty name.")
        if not component.type.strip():
            raise ValueError(f"Component '{component.name}' requires a type.")
        component_id = component.id or component.name
        if component_id in ids:
            raise ValueError(f"Duplicate component id '{component_id}'.")
        ids.append(component_id)

    for source, target in job.connections:
        if source not in ids or target not in ids:
            raise ValueError("Connection references unknown components.")

    # A small compatibility layer keeps the job format version stable.
    if job.version not in {"1.0", "1.1"}:
        raise ValueError(f"Unsupported job version: {job.version}")
