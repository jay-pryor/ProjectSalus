"""YAML-based loader for scenario configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from salus.models.scenario import ScenarioConfig
from salus.models.threat import DroneTrajectory

# Fields in the raw YAML dict that contain file paths needing resolution.
_PATH_FIELDS: tuple[str, ...] = (
    "site_dem_path",
    "site_dsm_path",
    "boundary_path",
    "trajectory_path",
)


def _load_trajectory(path: Path) -> DroneTrajectory:
    """Load a :class:`~salus.models.threat.DroneTrajectory` from a YAML file.

    Args:
        path: Absolute path to the trajectory YAML file.

    Returns:
        Validated :class:`~salus.models.threat.DroneTrajectory` instance.

    Raises:
        FileNotFoundError: If the trajectory file does not exist.
        OSError: If the file cannot be read.
        ValueError: If the YAML is invalid or fails model validation.
    """
    try:
        with path.open(encoding="utf-8") as fh:
            raw: Any = yaml.safe_load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"Trajectory file not found: {path}")
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in trajectory file {path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"Cannot read trajectory file {path}: {exc}") from exc

    if raw is None:
        raise ValueError(f"Trajectory file is empty: {path}")
    if not isinstance(raw, dict):
        raise ValueError(
            f"Trajectory file must be a YAML mapping, got {type(raw).__name__}: {path}"
        )
    payload: dict[str, Any] = raw
    try:
        return DroneTrajectory(**payload)
    except (ValidationError, TypeError) as exc:
        raise ValueError(f"Invalid trajectory configuration in {path}: {exc}") from exc


def load_scenario(path: str | Path) -> ScenarioConfig:
    """Load a ScenarioConfig from a YAML scenario file.

    Relative paths in the YAML (``site_dem_path``, ``site_dsm_path``,
    ``boundary_path``) are resolved relative to the scenario file's parent
    directory before Pydantic validation runs.

    Args:
        path: Path to the scenario YAML file. Resolved to an absolute path
            before opening to prevent path-traversal issues.

    Returns:
        Validated :class:`~salus.models.scenario.ScenarioConfig` instance
        with all path fields as absolute, resolved :class:`~pathlib.Path` objects.

    Raises:
        FileNotFoundError: If the scenario file does not exist.
        OSError: If the file cannot be read (permission denied, I/O error).
        ValueError: If the file is empty, contains invalid YAML, is not a
            top-level mapping, contains a non-string path field value, is
            missing required fields, or contains placement data that fails
            model validation.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    try:
        with path.open(encoding="utf-8") as fh:
            raw: Any = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in scenario file {path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"Cannot read scenario file {path}: {exc}") from exc

    if raw is None:
        raise ValueError(f"Scenario file is empty: {path}")
    if not isinstance(raw, dict):
        raise ValueError(f"Scenario file must be a YAML mapping, got {type(raw).__name__}: {path}")

    # Narrow the type once we know it is a dict.
    data: dict[str, Any] = raw

    # Discard any literal 'trajectory' key that may appear in the YAML —
    # the trajectory field is only populated by the loader via trajectory_path.
    # A raw dict under 'trajectory' would bypass _load_trajectory's validation.
    data.pop("trajectory", None)

    # Resolve relative paths against the scenario file's parent directory.
    scenario_dir = path.parent
    for field in _PATH_FIELDS:
        field_val = data.get(field)
        if field_val is not None:
            if not isinstance(field_val, (str, Path)):
                raise ValueError(
                    f"Scenario field '{field}' must be a string path, "
                    f"got {type(field_val).__name__}: {path}"
                )
            data[field] = (scenario_dir / str(field_val)).resolve()

    # If a trajectory path is present, load the DroneTrajectory YAML now so
    # the returned ScenarioConfig carries the parsed trajectory object.
    # traj_path_val is a resolved Path set by the loop above — assert the type
    # to narrow away Any from dict[str, Any].get().
    traj_path_val = data.get("trajectory_path")
    if traj_path_val is not None:
        traj_path: Path = (
            traj_path_val if isinstance(traj_path_val, Path) else Path(str(traj_path_val))
        )
        data["trajectory"] = _load_trajectory(traj_path)

    try:
        return ScenarioConfig(**data)
    except (ValidationError, TypeError) as exc:
        raise ValueError(f"Invalid scenario configuration in {path}: {exc}") from exc
