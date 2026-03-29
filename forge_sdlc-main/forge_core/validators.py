"""Forge config validators — schema validation with strict mode.

Validates .forge/ YAML/JSON config files against expected schemas.
Strict mode rejects unknown keys and requires version fields.
Also includes credential validators for live service checks.
"""

import ipaddress
import json
import re
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from forge_core.log import safe_log

__all__ = [
    "validate_config",
    "validate_credential",
    "validate_schema",
    "ConfigValidationError",
    "VALIDATORS",
]


class ConfigValidationError(Exception):
    """Raised when config validation fails."""


# ── Schema definitions ────────────────────────────────────────────────

CONFIG_SCHEMA = {
    "version": {"type": "str", "required": True},
    "project_name": {"type": "str", "required": True},
    "project_type": {"type": "str", "required": False, "allowed": ["python", "fullstack", "frontend"]},
    "governance_profile": {"type": "str", "required": False, "allowed": ["standard", "light"]},
    "standards": {"type": "list", "required": False},
    "excluded_standards": {"type": "list", "required": False},
    "review_agents": {"type": "list", "required": False},
    "hooks_enabled": {"type": "bool", "required": False},
    "cost_policy": {"type": "dict", "required": False},
    "exclusions": {"type": "dict", "required": False},
}

TRACKER_SCHEMA = {
    "version": {"type": "str", "required": True},
    "project": {"type": "str", "required": True},
    "phases": {"type": "list", "required": True},
}

STATE_SCHEMA = {
    "version": {"type": "str", "required": True},
    "current_session": {"type": "dict", "required": False},
    "history": {"type": "list", "required": False},
}

SERVICE_MAP_SCHEMA = {
    "version": {"type": "str", "required": True},
    "services": {"type": "dict", "required": True},
}

SCHEMAS = {
    "config": CONFIG_SCHEMA,
    "tracker": TRACKER_SCHEMA,
    "state": STATE_SCHEMA,
    "service_map": SERVICE_MAP_SCHEMA,
}


# ── Schema validation ────────────────────────────────────────────────


def validate_schema(
    data: dict[str, Any],
    schema: dict[str, dict],
    *,
    strict: bool = True,
    context: str = "",
) -> list[dict]:
    """Validate a dict against a schema definition.

    Parameters
    ----------
    data : dict
        The data to validate.
    schema : dict
        Schema definition mapping field names to type/required/allowed specs.
    strict : bool
        If True, unknown keys cause validation errors.
    context : str
        Optional context string for error messages (e.g. file path).

    Returns
    -------
    list[dict]
        List of validation errors. Empty list means valid.
    """
    errors: list[dict] = []
    prefix = f"{context}: " if context else ""

    if not isinstance(data, dict):
        return [{"field": "(root)", "message": f"{prefix}Expected dict, got {type(data).__name__}"}]

    # Check required fields
    for field, spec in schema.items():
        if spec.get("required") and field not in data:
            errors.append({
                "field": field,
                "message": f"{prefix}Required field '{field}' missing",
            })

    # Check types and allowed values
    for field, value in data.items():
        if field not in schema:
            if strict:
                errors.append({
                    "field": field,
                    "message": f"{prefix}Unknown field '{field}' (strict mode)",
                })
            continue

        spec = schema[field]
        expected_type = spec.get("type")
        if expected_type:
            type_map = {
                "str": str,
                "int": int,
                "float": (int, float),
                "bool": bool,
                "list": list,
                "dict": dict,
            }
            expected = type_map.get(expected_type)
            if expected and not isinstance(value, expected):
                errors.append({
                    "field": field,
                    "message": f"{prefix}Field '{field}' expected {expected_type}, got {type(value).__name__}",
                })

        allowed = spec.get("allowed")
        if allowed and value not in allowed:
            errors.append({
                "field": field,
                "message": f"{prefix}Field '{field}' value '{value}' not in {allowed}",
            })

    return errors


def validate_config(
    config_path: Path,
    schema_name: str = "config",
    *,
    strict: bool = True,
) -> dict:
    """Validate a YAML/JSON config file against a named schema.

    Parameters
    ----------
    config_path : Path
        Path to the config file.
    schema_name : str
        Name of schema to validate against (from SCHEMAS dict).
    strict : bool
        If True, unknown keys cause errors.

    Returns
    -------
    dict
        Result with success, errors, and file path.
    """
    schema = SCHEMAS.get(schema_name)
    if schema is None:
        return {
            "success": False,
            "action": "validate.config",
            "file": str(config_path),
            "error": f"Unknown schema: {schema_name}",
        }

    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "success": False,
            "action": "validate.config",
            "file": str(config_path),
            "error": f"Cannot read file: {exc}",
        }

    suffix = config_path.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content) or {}
        elif suffix == ".json":
            data = json.loads(content)
        else:
            return {
                "success": False,
                "action": "validate.config",
                "file": str(config_path),
                "error": f"Unsupported file format: {suffix}",
            }
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "action": "validate.config",
            "file": str(config_path),
            "error": f"Parse error: {exc}",
        }

    errors = validate_schema(data, schema, strict=strict, context=str(config_path))

    return {
        "success": len(errors) == 0,
        "action": "validate.config",
        "file": str(config_path),
        "schema": schema_name,
        "strict": strict,
        "errors": errors,
        "error_count": len(errors),
    }


# ── Credential validators ────────────────────────────────────────────
# Ported from v0.4.0 — live service connectivity checks

psycopg2: object | None = None
msal: object | None = None


def _ensure_psycopg2() -> None:
    global psycopg2  # noqa: PLW0603
    if psycopg2 is None:
        import psycopg2 as _pg  # type: ignore[no-redef]
        psycopg2 = _pg


def _ensure_msal() -> None:
    global msal  # noqa: PLW0603
    if msal is None:
        import msal as _msal  # type: ignore[no-redef]
        msal = _msal


def _timed(fn: Callable[..., dict], *args: object) -> dict:
    start = time.monotonic()
    try:
        result = fn(*args)
    except Exception as exc:
        result = {"status": "fail", "reason": str(exc)}
    elapsed = (time.monotonic() - start) * 1000
    result["duration_ms"] = round(elapsed, 2)
    return result


def _pg_connect(key: str, value: str) -> dict:
    _ensure_psycopg2()
    conn = psycopg2.connect(value, connect_timeout=5)  # type: ignore[union-attr]
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        row = cur.fetchone()
        if row and row[0] == 1:
            return {"status": "pass", "reason": "SELECT 1 succeeded"}
        return {"status": "fail", "reason": f"Unexpected result: {row}"}
    finally:
        conn.close()


def _gh_api_test(key: str, value: str) -> dict:
    resp = httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {value}"},
        timeout=10,
    )
    if resp.status_code == 200:
        return {"status": "pass", "reason": "GitHub API authenticated"}
    return {"status": "fail", "reason": f"GitHub API returned {resp.status_code}"}


def _reject_private_url(url: str) -> str | None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return "No hostname in URL"
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    except socket.gaierror:
        return f"Cannot resolve hostname: {hostname}"
    for _, _, _, _, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return f"URL resolves to private/internal IP: {ip}"
    return None


def _http_get(key: str, value: str) -> dict:
    rejection = _reject_private_url(value)
    if rejection:
        return {"status": "fail", "reason": f"SSRF blocked: {rejection}"}
    resp = httpx.get(value, timeout=10)
    if 200 <= resp.status_code < 300:
        return {"status": "pass", "reason": f"HTTP {resp.status_code}"}
    return {"status": "fail", "reason": f"HTTP {resp.status_code}"}


def _http_auth_get(key: str, value: str) -> dict:
    if len(value) >= 8:
        return {"status": "pass", "reason": f"Key length OK ({len(value)} chars)"}
    return {"status": "fail", "reason": f"Key too short ({len(value)} chars, minimum 8)"}


VALIDATORS: dict[str, Callable[[str, str], dict]] = {
    "pg_connect": _pg_connect,
    "gh_api_test": _gh_api_test,
    "http_get": _http_get,
    "http_auth_get": _http_auth_get,
}


def validate_credential(key: str, value: str, method: str) -> dict:
    """Validate a credential using the named method."""
    if method not in VALIDATORS:
        start = time.monotonic()
        result: dict[str, str | float] = {
            "status": "skipped",
            "reason": f"Unknown validation method: {method}",
        }
        result["duration_ms"] = round((time.monotonic() - start) * 1000, 2)
        return result
    return _timed(VALIDATORS[method], key, value)
