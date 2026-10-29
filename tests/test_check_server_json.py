"""scripts/check_server_json.py: server.json must carry the pyproject.toml version
and validate against the schema its $schema field names."""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_server_json.py"

# Stands in for the registry schema so the tests need no network access.
SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["description"],
    "properties": {"description": {"type": "string", "maxLength": 100}},
}


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)


def _write(
    root: Path,
    project: str,
    server: str,
    packages: list[str],
    description: str = "An MCP server",
) -> None:
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{project}"\n')
    (root / "schema.json").write_text(json.dumps(SCHEMA))
    doc = {
        "$schema": (root / "schema.json").as_uri(),
        "description": description,
        "version": server,
        "packages": [{"version": v} for v in packages],
    }
    (root / "server.json").write_text(json.dumps(doc))


def test_matching_versions_and_valid_schema_pass(tmp_path):
    _write(tmp_path, "1.2.3", "1.2.3", ["1.2.3", "1.2.3"])
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_server_version_mismatch_fails(tmp_path):
    _write(tmp_path, "1.2.3", "1.2.2", ["1.2.3"])
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "version" in result.stderr and "1.2.2" in result.stderr


def test_any_package_version_mismatch_fails(tmp_path):
    _write(tmp_path, "1.2.3", "1.2.3", ["1.2.3", "1.2.2"])
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "packages[1].version" in result.stderr


def test_schema_violation_fails(tmp_path):
    _write(tmp_path, "1.2.3", "1.2.3", ["1.2.3"], description="x" * 101)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "description" in result.stderr


def test_version_and_schema_errors_are_both_reported(tmp_path):
    _write(tmp_path, "1.2.3", "1.2.2", ["1.2.3"], description="x" * 101)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "1.2.2" in result.stderr and "description" in result.stderr
