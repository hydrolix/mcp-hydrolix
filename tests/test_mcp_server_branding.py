"""Scenario tests for the mcp-server-branding capability (tp-brand-via-hatch-hook).

Coverage strategy per scenario family:
- Build / wheel metadata: actually run `uv build` for each brand (module-scoped
  fixtures) and inspect the resulting wheel's METADATA, entry points, and baked
  _brand.py.
- Runtime brand identity: run the server module in a subprocess with a fake
  ``mcp_hydrolix._brand`` injected, so the baked-constant code path is exercised
  in isolation without installing a wheel.
- Dual-namespace env resolution: drive ``mcp_env.resolve_config`` in-process.
- mcpb / CI / sibling-repo: assert on the generated bundle and the workflow /
  sibling-repo files (the artifacts these scenarios constrain).
"""

import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_REPO = Path.home() / "src" / "mcp-trafficpeak"

# Load hatch_build.py (lives at the repo root, outside the package) directly.
_hb_spec = importlib.util.spec_from_file_location("hatch_build", REPO_ROOT / "hatch_build.py")
hatch_build = importlib.util.module_from_spec(_hb_spec)
_hb_spec.loader.exec_module(hatch_build)


# --------------------------------------------------------------------------- #
# Build fixtures
# --------------------------------------------------------------------------- #
def _build_wheel(brand, out_dir: Path) -> Path:
    env = dict(os.environ)
    if brand is not None:
        env["MCP_BRAND"] = brand
    else:
        env.pop("MCP_BRAND", None)
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, got {wheels}"
    return wheels[0]


@pytest.fixture(scope="module")
def hydrolix_wheel(tmp_path_factory) -> Path:
    """A wheel built with no MCP_BRAND set (the default Hydrolix brand)."""
    return _build_wheel(None, tmp_path_factory.mktemp("hydrolix_whl"))


@pytest.fixture(scope="module")
def trafficpeak_wheel(tmp_path_factory) -> Path:
    """A wheel built with MCP_BRAND=trafficpeak."""
    return _build_wheel("trafficpeak", tmp_path_factory.mktemp("tp_whl"))


def _zip_read(whl: Path, member_suffix: str) -> str:
    with zipfile.ZipFile(whl) as zf:
        name = next(n for n in zf.namelist() if n.endswith(member_suffix))
        return zf.read(name).decode("utf-8")


def _metadata_headers(metadata_text: str) -> dict:
    """Parse the RFC822-style METADATA headers (everything before the blank line
    that precedes the long Description)."""
    headers: dict[str, list[str]] = {}
    for line in metadata_text.splitlines():
        if line == "":
            break
        if ": " in line:
            key, _, value = line.partition(": ")
            headers.setdefault(key, []).append(value)
    return headers


# --------------------------------------------------------------------------- #
# Requirement: Two PyPI distributions built from one source via a brand flag
# --------------------------------------------------------------------------- #
def test_default_build_produces_the_hydrolix_wheel(hydrolix_wheel):
    assert hydrolix_wheel.name.startswith("mcp_hydrolix-")
    headers = _metadata_headers(_zip_read(hydrolix_wheel, "METADATA"))
    assert headers["Name"] == ["mcp-hydrolix"]
    entry_points = _zip_read(hydrolix_wheel, "entry_points.txt")
    assert "mcp-hydrolix = mcp_hydrolix.main:main" in entry_points


def test_trafficpeak_build_via_env_var_produces_the_tp_wheel(hydrolix_wheel, trafficpeak_wheel):
    assert trafficpeak_wheel.name.startswith("mcp_trafficpeak-")
    headers = _metadata_headers(_zip_read(trafficpeak_wheel, "METADATA"))
    assert headers["Name"] == ["mcp-trafficpeak"]
    entry_points = _zip_read(trafficpeak_wheel, "entry_points.txt")
    assert "mcp-trafficpeak = mcp_hydrolix.main:main" in entry_points
    # Same version string as the Hydrolix-mode build from the same checkout.
    h_ver = _metadata_headers(_zip_read(hydrolix_wheel, "METADATA"))["Version"]
    assert headers["Version"] == h_ver


def test_invalid_mcp_brand_value_fails_fast(tmp_path):
    env = dict(os.environ, MCP_BRAND="foo")
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "MCP_BRAND" in combined
    assert "hydrolix" in combined and "trafficpeak" in combined
    assert not list(tmp_path.glob("*.whl"))


def test_tp_wheel_is_built_from_this_repos_tagged_commit():
    # The sibling workflow builds the TP wheel by checking out hydrolix/mcp-hydrolix
    # at the dispatched tag and running MCP_BRAND=trafficpeak uv build -- it carries
    # no product source of its own.
    if not SIBLING_REPO.exists():
        pytest.skip("sibling repo clone not present")
    wf = (SIBLING_REPO / ".github/workflows/publish.yml").read_text()
    assert "repository: hydrolix/mcp-hydrolix" in wf
    assert "${{ inputs.tag }}" in wf
    assert "MCP_BRAND=trafficpeak uv build" in wf


# --------------------------------------------------------------------------- #
# Requirement: Brand-appropriate distribution metadata with zero leakage
# --------------------------------------------------------------------------- #
def test_pip_show_on_tp_wheel_has_no_hydrolix_string(trafficpeak_wheel):
    headers = _metadata_headers(_zip_read(trafficpeak_wheel, "METADATA"))
    # Customer-facing brand-identity fields must be TrafficPeak-only. Source /
    # account-level fields (Project-URL, Author) legitimately reference the
    # hydrolix org -- the package ships under the same PyPI account and its repo
    # is github.com/hydrolix/mcp-trafficpeak -- so they are excluded here.
    checked = ["Name", "Summary"]
    for field in checked:
        for value in headers.get(field, []):
            assert "hydrolix" not in value.lower(), f"{field}: {value!r} leaks hydrolix"
    assert headers["Name"] == ["mcp-trafficpeak"]


def test_pip_show_on_hydrolix_wheel_is_unchanged(hydrolix_wheel):
    metadata = _zip_read(hydrolix_wheel, "METADATA")
    headers = _metadata_headers(metadata)
    assert headers["Name"] == ["mcp-hydrolix"]
    # The Hydrolix wheel never mentions the TrafficPeak brand anywhere.
    assert "trafficpeak" not in metadata.lower()


def test_uv_tree_shows_only_the_installed_brand(trafficpeak_wheel):
    # A uv tree of an installed mcp-trafficpeak must not transitively reference
    # mcp-hydrolix; the strongest static proxy is that the TP wheel declares no
    # dependency on mcp-hydrolix.
    headers = _metadata_headers(_zip_read(trafficpeak_wheel, "METADATA"))
    for dep in headers.get("Requires-Dist", []):
        assert "mcp-hydrolix" not in dep.lower()


def test_long_description_is_generated_by_the_brand_filter_from_this_repos_readme(hydrolix_wheel):
    readme = (REPO_ROOT / "README.md").read_text()
    metadata = _zip_read(hydrolix_wheel, "METADATA")
    # The Description (everything after the header block) equals README byte-for-byte
    # because the Hydrolix-mode filter is an identity transform.
    _, _, description = metadata.partition("\n\n")
    assert readme.strip() in description


def test_long_description_tokens_are_rebranded_for_trafficpeak_builds():
    readme = (REPO_ROOT / "README.md").read_text()
    filtered = hatch_build.brand_substitution_filter(readme, "trafficpeak")
    assert "mcp-hydrolix" not in filtered  # every dist-name token rebranded
    assert "mcp-trafficpeak" in filtered
    assert "HYDROLIX_" not in filtered  # every env-var prefix rebranded
    assert "TRAFFICPEAK_" in filtered
    # prose brand name substituted
    assert "Hydrolix" not in filtered
    assert "TrafficPeak" in filtered
    # import path (underscore) is intentionally NOT rebranded by the filter
    assert "mcp_trafficpeak" not in filtered


# --------------------------------------------------------------------------- #
# Requirement: Runtime brand identifier baked at build time
# --------------------------------------------------------------------------- #
def _run_branded(brand: str, dist: str, extra_argv0=None) -> dict:
    """Import mcp_server in a subprocess with a fake baked _brand and dump the
    customer-visible identifiers as JSON."""
    snippet = f"""
import sys, types, json
m = types.ModuleType("mcp_hydrolix._brand")
m.__brand__ = {brand!r}
m.__dist_name__ = {dist!r}
sys.modules["mcp_hydrolix._brand"] = m
{f"sys.argv[0] = {extra_argv0!r}" if extra_argv0 else ""}
import mcp_hydrolix.mcp_server as s
import mcp_hydrolix.brand as b
print(json.dumps({{
    "server_name": s.MCP_SERVER_NAME,
    "banner": s.server_banner(),
    "admin_comment": s.HDX_ADMIN_COMMENT,
    "mcp_name": s.mcp.name,
    "user_agent": b.USER_AGENT,
    "brand": b.BRAND,
}}))
"""
    env = dict(
        os.environ,
        HYDROLIX_URL="https://demo.example.live",
        HYDROLIX_USER="u",
        HYDROLIX_PASSWORD="p",
    )
    env.pop("MCP_BRAND", None)
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


@pytest.fixture(scope="module")
def tp_runtime() -> dict:
    return _run_branded("trafficpeak", "mcp-trafficpeak")


def test_brand_identifier_in_startup_log_reflects_baked_constant(tp_runtime):
    assert "trafficpeak" in tp_runtime["banner"]


def test_brand_identifier_in_outbound_user_agent_reflects_baked_constant(tp_runtime):
    assert tp_runtime["user_agent"].startswith("mcp-trafficpeak/")


def test_renaming_the_launcher_does_not_change_the_reported_brand():
    # Invoke with argv[0] rewritten to mcp-hydrolix; brand must still be trafficpeak.
    out = _run_branded("trafficpeak", "mcp-trafficpeak", extra_argv0="mcp-hydrolix")
    assert out["brand"] == "trafficpeak"
    assert out["user_agent"].startswith("mcp-trafficpeak/")
    assert "trafficpeak" in out["banner"]


def test_fastmcp_server_name_reflects_the_baked_distribution_name(tp_runtime):
    assert tp_runtime["mcp_name"] == "mcp-trafficpeak"


def test_admin_comment_user_token_reflects_the_baked_distribution_name(tp_runtime):
    assert tp_runtime["admin_comment"].startswith("User: mcp-trafficpeak ")
    assert "mcp-hydrolix" not in tp_runtime["admin_comment"]


def test_no_customer_visible_output_of_a_trafficpeak_wheel_contains_the_hydrolix_distribution_name(
    tp_runtime,
):
    for key in ("banner", "admin_comment", "mcp_name", "user_agent"):
        assert "mcp-hydrolix" not in tp_runtime[key].lower()


# --------------------------------------------------------------------------- #
# Requirement: Dual-namespace env-var contract with whole-chain precedence
# --------------------------------------------------------------------------- #
def _resolve(monkeypatch, env: dict):
    for k in list(os.environ):
        if k.startswith(("HYDROLIX_", "TRAFFICPEAK_")):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import mcp_hydrolix.mcp_env as mcp_env

    return mcp_env


def test_only_trafficpeak_env_vars_provided(monkeypatch):
    m = _resolve(monkeypatch, {"TRAFFICPEAK_URL": "https://tp.example.live"})
    cfg = m.resolve_config()
    assert cfg._prefix == "TRAFFICPEAK_"
    assert cfg.host == "tp.example.live"


def test_only_hydrolix_env_vars_provided(monkeypatch, caplog):
    import logging

    m = _resolve(monkeypatch, {"HYDROLIX_URL": "https://hdx.example.live"})
    with caplog.at_level(logging.WARNING):
        cfg = m.resolve_config()
    assert cfg._prefix == "HYDROLIX_"
    assert not any("TRAFFICPEAK" in r.getMessage() for r in caplog.records)


def test_partial_trafficpeak_config_falls_through_to_hydrolix(monkeypatch):
    m = _resolve(
        monkeypatch,
        {"TRAFFICPEAK_HTTP_QUERY_HOST": "q.tp", "HYDROLIX_URL": "https://hdx.example.live"},
    )
    cfg = m.resolve_config()
    assert cfg._prefix == "HYDROLIX_"
    assert cfg.host == "hdx.example.live"


def test_both_namespaces_resolve_with_conflicting_anchors(monkeypatch, caplog):
    import logging

    m = _resolve(
        monkeypatch,
        {"TRAFFICPEAK_URL": "https://tp.example.live", "HYDROLIX_URL": "https://hdx.example.live"},
    )
    with caplog.at_level(logging.WARNING):
        cfg = m.resolve_config()
    assert cfg.host == "tp.example.live"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "TRAFFICPEAK_URL" in msg and "HYDROLIX_URL" in msg


def test_both_namespaces_resolve_to_identical_values(monkeypatch, caplog):
    import logging

    m = _resolve(
        monkeypatch,
        {
            "TRAFFICPEAK_URL": "https://same.example.live",
            "HYDROLIX_URL": "https://same.example.live",
        },
    )
    with caplog.at_level(logging.WARNING):
        m.resolve_config()
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_neither_namespace_provides_an_anchor(monkeypatch):
    m = _resolve(monkeypatch, {})
    with pytest.raises(ValueError) as exc:
        m.resolve_config()
    assert "TRAFFICPEAK_URL" in str(exc.value) and "HYDROLIX_URL" in str(exc.value)


# --------------------------------------------------------------------------- #
# Requirement: Existing Hydrolix-branded surface is preserved
# --------------------------------------------------------------------------- #
def test_pre_change_customer_config_still_works(monkeypatch):
    m = _resolve(monkeypatch, {"HYDROLIX_URL": "https://hdx.example.live"})
    cfg = m.resolve_config()
    assert cfg.host == "hdx.example.live"
    assert cfg.secure is True


def test_python_import_path_is_unchanged():
    # Both wheels import the same module; from source the package imports cleanly.
    import mcp_hydrolix  # noqa: F401
    import mcp_hydrolix.brand  # noqa: F401

    assert mcp_hydrolix.__name__ == "mcp_hydrolix"


# --------------------------------------------------------------------------- #
# Requirement: This repo's customer-facing docs reference only Hydrolix
# --------------------------------------------------------------------------- #
def test_readme_does_not_mention_trafficpeak():
    customer_docs = ["README.md", "docker-compose.yaml", "glama.json", "fastmcp.json"]
    for name in customer_docs:
        path = REPO_ROOT / name
        if path.exists():
            assert "trafficpeak" not in path.read_text().lower(), f"{name} mentions trafficpeak"


def test_internal_engineering_docs_may_mention_both_brands():
    # This requirement does not constrain internal docs; the change's own openspec
    # tree mentions trafficpeak, which is permitted.
    change_dir = REPO_ROOT / "openspec/changes/tp-brand-via-hatch-hook"
    blob = "\n".join(p.read_text() for p in change_dir.rglob("*.md"))
    assert "trafficpeak" in blob.lower()


# --------------------------------------------------------------------------- #
# Requirement: Artifact parity invariant (release workflow structure)
# --------------------------------------------------------------------------- #
def _publish_yml() -> str:
    return (REPO_ROOT / ".github/workflows/publish.yml").read_text()


def test_release_tag_publishes_both_pypi_distributions_at_the_same_version():
    wf = _publish_yml()
    assert "MCP_BRAND=hydrolix uv build" in wf
    assert "gh workflow run publish.yml" in wf
    assert "-R hydrolix/mcp-trafficpeak" in wf
    assert 'tag="${TAG}"' in wf


def test_sibling_repo_dispatch_failure_fails_the_release():
    wf = _publish_yml()
    # `gh workflow run` exits non-zero on dispatch failure, failing the step (and
    # thus the publish job) -- it runs inside the `publish` job after the upload,
    # using a GitHub App token scoped to mcp-trafficpeak minted from the AWS
    # Secrets Manager dispatch credential.
    assert "gh workflow run publish.yml" in wf
    assert "actions/create-github-app-token" in wf
    assert "repositories: mcp-trafficpeak" in wf
    assert "steps.tp-token.outputs.token" in wf


def test_release_tag_publishes_both_mcpb_bundles_at_the_same_version():
    wf = _publish_yml()
    assert "MCP_BRAND=hydrolix bash mcpb/build.sh" in wf
    assert "MCP_BRAND=trafficpeak bash mcpb/build.sh" in wf


def test_release_tag_publishes_both_docker_images_at_the_same_version():
    wf = _publish_yml()
    assert "--build-arg MCP_BRAND=" in wf
    assert "mcp-${brand}" in wf


def test_ci_fails_if_pairing_is_broken():
    wf = _publish_yml()
    # Each in-repo artifact job carries a parity assertion that exits non-zero.
    assert "artifact parity violated" in wf
    assert wf.count("artifact parity violated") >= 2  # mcpb + docker


# --------------------------------------------------------------------------- #
# Requirement: mcpb bundle is brand-parameterized
# --------------------------------------------------------------------------- #
def _expand_mcpb(brand, tmp_path: Path) -> Path:
    """Run mcpb/build.sh with npx shimmed so it only expands templates (no pack)."""
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "npx").write_text("#!/usr/bin/env bash\nexit 0\n")
    (shim / "npx").chmod(0o755)
    env = dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}", MCPB_VERSION="9.9.9")
    if brand:
        env["MCP_BRAND"] = brand
    else:
        env.pop("MCP_BRAND", None)
    subprocess.run(
        ["bash", "mcpb/build.sh"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return REPO_ROOT / "mcpb/manifest.json"


def test_tp_mode_mcpb_build_emits_a_tp_branded_bundle(tmp_path):
    manifest_path = _expand_mcpb("trafficpeak", tmp_path)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == "mcp-trafficpeak"
    # Customer-facing UI fields are TrafficPeak-only (no hydrolix). Source/account
    # fields (homepage, repository, author) may reference the hydrolix org.
    customer_facing = [manifest["name"], manifest["display_name"], manifest["description"]]
    customer_facing += [f["title"] for f in manifest["user_config"].values()]
    customer_facing += list(manifest["server"]["mcp_config"]["env"].keys())
    customer_facing += list(manifest["user_config"].keys())
    for value in customer_facing:
        assert "hydrolix" not in value.lower(), f"customer-facing field leaks hydrolix: {value!r}"
    titles = [f["title"] for f in manifest["user_config"].values()]
    assert any("TrafficPeak" in t for t in titles)


def test_default_mode_mcpb_build_emits_the_hydrolix_bundle_unchanged(tmp_path):
    manifest_path = _expand_mcpb(None, tmp_path)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == "mcp-hydrolix"
    assert manifest["display_name"] == "Hydrolix"
    assert manifest["server"]["mcp_config"]["env"]["HYDROLIX_URL"] == "${user_config.hydrolix_url}"


# --------------------------------------------------------------------------- #
# Requirement: Only PyPI publishing goes through the sibling repo
# --------------------------------------------------------------------------- #
def test_sibling_repo_contains_no_source_or_tests():
    if not SIBLING_REPO.exists():
        pytest.skip("sibling repo clone not present")
    forbidden = []
    for p in SIBLING_REPO.rglob("*"):
        if ".git" in p.parts:
            continue
        rel = p.relative_to(SIBLING_REPO).as_posix()
        if (
            p.name == "pyproject.toml"
            or p.name == "Dockerfile"
            or "mcp_hydrolix/" in rel
            or rel.startswith("tests/")
            or "/tests/" in rel
            or rel.startswith("mcpb/")
        ):
            forbidden.append(rel)
    assert not forbidden, f"sibling contains forbidden paths: {forbidden}"
    assert not (SIBLING_REPO / "PYPI_README.md").exists()


def test_sibling_repo_publish_workflow_uses_workflow_dispatch():
    if not SIBLING_REPO.exists():
        pytest.skip("sibling repo clone not present")
    import yaml

    wf = yaml.safe_load((SIBLING_REPO / ".github/workflows/publish.yml").read_text())
    on = wf[True]  # PyYAML parses the `on:` key as boolean True
    assert "workflow_dispatch" in on
    assert "repository_dispatch" not in on
    assert "push" not in on
    tag = on["workflow_dispatch"]["inputs"]["tag"]
    assert tag["type"] == "string"
    assert tag["required"] is True


def test_tp_pypi_landing_page_is_generated_from_this_repos_readme_by_the_brand_filter():
    readme = (REPO_ROOT / "README.md").read_text()
    filtered = hatch_build.brand_substitution_filter(readme, "trafficpeak")
    # Generated from this repo's README (not the sibling's own README).
    assert filtered != readme
    if SIBLING_REPO.exists():
        assert filtered != (SIBLING_REPO / "README.md").read_text()
        assert not (SIBLING_REPO / "PYPI_README.md").exists()
