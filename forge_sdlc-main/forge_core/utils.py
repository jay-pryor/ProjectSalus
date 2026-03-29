"""Forge shared utilities — canonical helper functions used across modules."""

import re

TASK_ID_PATTERN = re.compile(r"^S\d+\.P\d+\.T\d+$")
PHASE_ID_PATTERN = re.compile(r"^S\d+\.P\d+$")


def to_snake_case(name: str) -> str:
    """Convert a name string to snake_case for file naming."""
    name = name.lower().strip()
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")
