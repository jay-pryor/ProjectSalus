"""Forge config sync validator — catches drift between config and reality.

Validates that Forge configuration accurately reflects the actual
project state: service map entries, healthcheck endpoints, port
assignments, and repo structure.
"""

import os
import re
from pathlib import Path

import yaml

from forge_core.log import safe_log

__all__ = ["ConfigSyncValidator"]


class ConfigSyncValidator:
    """Validates config consistency between Forge config and actual state."""

    def __init__(self, forge_root: Path | None = None) -> None:
        if forge_root is not None:
            self._forge_root = Path(forge_root).resolve()
        else:
            env_dir = os.environ.get("FORGE_ROOT")
            self._forge_root = Path(env_dir).resolve() if env_dir else Path.cwd().resolve()

    def _load_yaml(self, path: Path) -> dict | None:
        try:
            content = path.read_text(encoding="utf-8")
            return yaml.safe_load(content) or {}
        except (OSError, yaml.YAMLError):
            return None

    def check_service_map(self, service_map_path: Path | None = None) -> list[dict]:
        """Validate service map entries match actual repos on disk."""
        findings = []
        if service_map_path is None:
            service_map_path = self._forge_root / "forge_remediation" / "service_map.yaml"
        
        data = self._load_yaml(service_map_path)
        if data is None:
            findings.append({
                "check": "service_map",
                "status": "skip",
                "message": f"Cannot load service map: {service_map_path}",
            })
            return findings

        services = data.get("services", {})
        for name, config in services.items():
            repo_path = config.get("repo")
            if repo_path:
                full_path = Path(repo_path).expanduser()
                if not full_path.is_dir():
                    findings.append({
                        "check": "service_map.repo_exists",
                        "status": "fail",
                        "service": name,
                        "message": f"Repo path does not exist: {repo_path}",
                    })
                else:
                    # Check for .forge/ dir in repo
                    forge_dir = full_path / ".forge"
                    if not forge_dir.is_dir():
                        findings.append({
                            "check": "service_map.forge_init",
                            "status": "warning",
                            "service": name,
                            "message": f"Repo missing .forge/ directory: {repo_path}",
                        })
        return findings

    def check_port_conflicts(self, service_map_path: Path | None = None) -> list[dict]:
        """Check for port assignment conflicts in service map."""
        findings = []
        if service_map_path is None:
            service_map_path = self._forge_root / "forge_remediation" / "service_map.yaml"
        
        data = self._load_yaml(service_map_path)
        if data is None:
            return findings

        services = data.get("services", {})
        port_map: dict[int, list[str]] = {}
        for name, config in services.items():
            port = config.get("port")
            if port:
                port_map.setdefault(int(port), []).append(name)

        for port, services_on_port in port_map.items():
            if len(services_on_port) > 1:
                findings.append({
                    "check": "port_conflicts",
                    "status": "fail",
                    "message": f"Port {port} assigned to multiple services: {', '.join(services_on_port)}",
                })
        return findings

    def check_healthcheck_endpoints(self, service_map_path: Path | None = None) -> list[dict]:
        """Verify healthcheck endpoints exist in codebase."""
        findings = []
        if service_map_path is None:
            service_map_path = self._forge_root / "forge_remediation" / "service_map.yaml"
        
        data = self._load_yaml(service_map_path)
        if data is None:
            return findings

        services = data.get("services", {})
        for name, config in services.items():
            healthcheck = config.get("healthcheck")
            repo_path = config.get("repo")
            if healthcheck and repo_path:
                full_path = Path(repo_path).expanduser()
                if full_path.is_dir():
                    # Search for health endpoint registration
                    found = False
                    for py_file in full_path.rglob("*.py"):
                        try:
                            content = py_file.read_text(encoding="utf-8", errors="replace")
                            if re.search(r"""['"]/health['"]\s*\)|health_?check""", content, re.IGNORECASE):
                                found = True
                                break
                        except OSError:
                            continue
                    if not found:
                        findings.append({
                            "check": "healthcheck_endpoints",
                            "status": "warning",
                            "service": name,
                            "message": f"Healthcheck endpoint '{healthcheck}' not found in {repo_path}",
                        })
        return findings

    def check_remediation_refs(self) -> list[dict]:
        """Verify remediation configs reference valid services."""
        findings = []
        service_map_path = self._forge_root / "forge_remediation" / "service_map.yaml"
        data = self._load_yaml(service_map_path)
        if data is None:
            return findings

        valid_services = set(data.get("services", {}).keys())
        
        # Check triage_rules.yaml
        triage_path = self._forge_root / "forge_remediation" / "triage_rules.yaml"
        triage_data = self._load_yaml(triage_path)
        if triage_data:
            rules = triage_data.get("rules", [])
            for rule in rules:
                services = rule.get("services", [])
                for svc in services:
                    if svc not in valid_services and svc != "*":
                        findings.append({
                            "check": "remediation_refs",
                            "status": "fail",
                            "message": f"Triage rule references unknown service: {svc}",
                        })

        # Check rollback_policy.yaml
        rollback_path = self._forge_root / "forge_remediation" / "rollback_policy.yaml"
        rollback_data = self._load_yaml(rollback_path)
        if rollback_data:
            policies = rollback_data.get("policies", {})
            for svc in policies:
                if svc not in valid_services and svc != "default":
                    findings.append({
                        "check": "remediation_refs",
                        "status": "fail",
                        "message": f"Rollback policy references unknown service: {svc}",
                    })
        return findings

    def validate_all(self) -> dict:
        """Run all config sync checks."""
        all_findings: list[dict] = []
        all_findings.extend(self.check_service_map())
        all_findings.extend(self.check_port_conflicts())
        all_findings.extend(self.check_healthcheck_endpoints())
        all_findings.extend(self.check_remediation_refs())

        fail_count = sum(1 for f in all_findings if f.get("status") == "fail")
        warning_count = sum(1 for f in all_findings if f.get("status") == "warning")

        return {
            "success": fail_count == 0,
            "action": "config-sync.validate",
            "finding_count": len(all_findings),
            "fail_count": fail_count,
            "warning_count": warning_count,
            "findings": all_findings,
        }
