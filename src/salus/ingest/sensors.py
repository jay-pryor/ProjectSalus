"""YAML-based loader for sensor and effector definitions."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from salus.models.sensor import EffectorDefinition, SensorDefinition

T = TypeVar("T", bound=BaseModel)

_YAML_SUFFIXES = (".yaml", ".yml")


def _load_yaml_records(path: Path) -> list[dict[str, Any]]:
    """Read a YAML file and return a list of validated record dicts.

    Supports both a single mapping (one record) and a sequence of mappings
    (multiple records) at the top level. Each element in a list is validated
    to be a mapping before returning.

    Raises:
        OSError: If the file cannot be opened (permission denied, missing, etc.).
        ValueError: If the file contains invalid YAML, an unexpected top-level
            type, or list elements that are not mappings.
    """
    try:
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"Cannot read {path}: {exc}") from exc

    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Entry {i} in {path} is not a mapping (got {type(item).__name__})"
                )
        return raw
    raise ValueError(f"Expected a mapping or list of mappings in {path}, got {type(raw).__name__}")


def _load_definitions(
    directory: str | Path,
    model_cls: type[T],
    label: str,
) -> list[T]:
    """Load all YAML files in *directory* as instances of *model_cls*.

    Args:
        directory: Path to the directory containing YAML files.
        model_cls: Pydantic model class to instantiate for each record.
        label: Human-readable label used in error and warning messages.

    Returns:
        List of validated model instances in filename order. May be empty if
        the directory contains no YAML files — callers must check length before
        use to avoid a zero-sensor/effector simulation run.

    Raises:
        FileNotFoundError: If *directory* does not exist.
        NotADirectoryError: If *directory* exists but is not a directory.
        PermissionError: If *directory* exists but cannot be listed.
        OSError: If any YAML file cannot be opened.
        ValueError: If any YAML file contains invalid syntax, an unexpected
            structure, or data that fails model validation. The filename and
            entry index are included in the message.
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"{label} directory not found: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"{label} path is not a directory: {directory}")

    try:
        yaml_files = sorted(p for p in directory.iterdir() if p.suffix.lower() in _YAML_SUFFIXES)
    except PermissionError as exc:
        raise PermissionError(f"Cannot list {label} directory {directory}: {exc}") from exc

    if not yaml_files:
        warnings.warn(
            f"No YAML files found in {label} directory: {directory}",
            stacklevel=3,
        )
        return []

    results: list[T] = []
    for path in yaml_files:
        records = _load_yaml_records(path)
        for i, record in enumerate(records):
            try:
                # Pydantic's ValidationError provides runtime type enforcement
                # for record fields — mypy cannot verify **dict[str, Any] here.
                results.append(model_cls(**record))
            except (ValidationError, TypeError) as exc:
                raise ValueError(
                    f"Invalid {label} definition at entry {i} in {path}: {exc}"
                ) from exc

    return results


def load_sensors(directory: str | Path) -> list[SensorDefinition]:
    """Load all SensorDefinition records from YAML files in *directory*.

    Each YAML file may contain a single sensor mapping or a list of mappings.

    Args:
        directory: Path to the directory containing sensor YAML files.

    Returns:
        List of validated SensorDefinition instances. Returns an empty list
        (with a warning) if no YAML files are found — callers should check
        that the list is non-empty before proceeding.

    Raises:
        FileNotFoundError: If *directory* does not exist.
        PermissionError: If *directory* cannot be listed.
        OSError: If any YAML file cannot be opened.
        ValueError: If any file contains invalid YAML or fails validation.
    """
    return _load_definitions(directory, SensorDefinition, "sensor")


def load_effectors(directory: str | Path) -> list[EffectorDefinition]:
    """Load all EffectorDefinition records from YAML files in *directory*.

    Each YAML file may contain a single effector mapping or a list of mappings.

    Args:
        directory: Path to the directory containing effector YAML files.

    Returns:
        List of validated EffectorDefinition instances. Returns an empty list
        (with a warning) if no YAML files are found — callers should check
        that the list is non-empty before proceeding.

    Raises:
        FileNotFoundError: If *directory* does not exist.
        PermissionError: If *directory* cannot be listed.
        OSError: If any YAML file cannot be opened.
        ValueError: If any file contains invalid YAML or fails validation.
    """
    return _load_definitions(directory, EffectorDefinition, "effector")
