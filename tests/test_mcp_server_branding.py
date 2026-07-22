"""Tests for the dual-brand (mcp-hydrolix / mcp-trafficpeak) surface.

Covers the OpenSpec change ``tp-brand-via-hatch-hook``. This module currently
holds the dual-namespace env-var scenarios (Requirement: Dual-Namespace Env-Var
Contract With Whole-Chain Precedence); build/metadata and mcpb scenarios live
alongside as they are implemented.
"""

import email
import logging
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import hatch_build
from mcp_hydrolix import mcp_env
from mcp_hydrolix.mcp_env import HydrolixConfig, brand_getenv

REPO_ROOT = Path(__file__).resolve().parent.parent
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


@pytest.fixture
def brand_env():
    """Isolate brand env-var state: start clean, fully restore os.environ after.

    Clears any inherited HYDROLIX_*/TRAFFICPEAK_* vars so each test starts from a
    known slate, and restores the original environment on teardown.
    """
    saved = dict(os.environ)
    for key in [k for k in os.environ if k.startswith(("HYDROLIX_", "TRAFFICPEAK_"))]:
        del os.environ[key]
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_only_trafficpeak_env_vars_provided(brand_env, caplog):
    brand_env["TRAFFICPEAK_URL"] = "https://tp.example.live"
    brand_env["TRAFFICPEAK_QUERY_POOL"] = "tp-pool"
    with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
        config = HydrolixConfig()
    # TRAFFICPEAK_* is honored at read time via brand_getenv.
    assert config.host == "tp.example.live"
    assert config.query_pool == "tp-pool"
    # No os.environ mutation: the canonical HYDROLIX_* names are NOT written.
    assert "HYDROLIX_URL" not in os.environ
    assert "HYDROLIX_QUERY_POOL" not in os.environ
    # Silent: no conflict warning when only TrafficPeak is configured.
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_only_hydrolix_env_vars_provided(brand_env, caplog):
    brand_env["HYDROLIX_URL"] = "https://hdx.example.live"
    with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
        config = HydrolixConfig()
    assert config.host == "hdx.example.live"
    # No TRAFFICPEAK_* anchor -> environment untouched, no warning emitted.
    assert "TRAFFICPEAK_URL" not in os.environ
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_trafficpeak_overrides_apply_per_variable_over_hydrolix_fallback(brand_env):
    # Per-variable precedence: a TRAFFICPEAK_* override wins for its own variable,
    # while variables set only under HYDROLIX_* are used unchanged (silent
    # fallback). Here the query host comes from TRAFFICPEAK_*, the URL-derived
    # version-api host from HYDROLIX_URL -- a deliberate mixed resolution.
    brand_env["TRAFFICPEAK_HTTP_QUERY_HOST"] = "tp-query-host"
    brand_env["HYDROLIX_URL"] = "https://hdx.example.live"
    config = HydrolixConfig()
    assert config.host == "tp-query-host"  # TP override wins per-variable
    assert config.version_api_host == "hdx.example.live"  # HYDROLIX_URL fallback


def test_hydrolix_operational_defaults_survive_a_trafficpeak_url(brand_env):
    # Regression: an operational var set only under HYDROLIX_* (as a container
    # image does) MUST survive when the caller supplies only TRAFFICPEAK_URL --
    # the resolver no longer deletes the Hydrolix namespace.
    brand_env["HYDROLIX_MCP_SERVER_TRANSPORT"] = "http"
    brand_env["HYDROLIX_MCP_BIND_HOST"] = "0.0.0.0"
    brand_env["TRAFFICPEAK_URL"] = "https://tp.example.live"
    config = HydrolixConfig()
    assert config.host == "tp.example.live"  # TP URL projected
    assert config.mcp_server_transport == "http"  # HYDROLIX_* operational default kept
    assert config.mcp_bind_host == "0.0.0.0"


def test_both_namespaces_resolve_with_conflicting_anchors(brand_env, caplog):
    brand_env["TRAFFICPEAK_URL"] = "https://tp.example.live"
    brand_env["HYDROLIX_URL"] = "https://hdx.example.live"
    with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
        config = HydrolixConfig()
    # Per-variable precedence: TrafficPeak wins for URL, silently -- no conflict
    # warning (the whole-chain conflict-advisory was removed by design).
    assert config.host == "tp.example.live"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_both_namespaces_resolve_to_identical_values(brand_env, caplog):
    brand_env["TRAFFICPEAK_URL"] = "https://same.example.live"
    brand_env["HYDROLIX_URL"] = "https://same.example.live"
    with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
        config = HydrolixConfig()
    assert config.host == "same.example.live"
    # Identical anchors -> silent.
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_neither_namespace_provides_an_anchor(brand_env):
    # Default (stdio) transport, no anchor in either namespace -> hard failure.
    # The committed brand is Hydrolix, so the message names HYDROLIX_URL and,
    # per the no-cross-leak rule, must NOT mention TrafficPeak.
    with pytest.raises(ValueError) as excinfo:
        HydrolixConfig()
    msg = str(excinfo.value)
    assert "HYDROLIX_URL" in msg
    assert "trafficpeak" not in msg.lower()


def test_hydrolix_branded_errors_never_mention_trafficpeak(brand_env, monkeypatch):
    # Exercise both connection-target error paths under the Hydrolix brand. The
    # hint derives from the baked own env prefix; a Hydrolix wheel bakes "HYDROLIX_".
    monkeypatch.setattr(mcp_env, "__env_prefix__", "HYDROLIX_")
    with pytest.raises(ValueError) as stdio_err:  # stdio: no anchor
        HydrolixConfig()
    assert "trafficpeak" not in str(stdio_err.value).lower()
    monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "http")
    with pytest.raises(ValueError) as http_err:  # http: URL required
        HydrolixConfig()
    assert "trafficpeak" not in str(http_err.value).lower()


def test_trafficpeak_branded_error_names_trafficpeak_anchor(brand_env, monkeypatch):
    # Under the TrafficPeak brand the error leads with TRAFFICPEAK_URL and does
    # not need to mention HYDROLIX_URL. The hint derives from the baked own
    # env prefix (__env_prefix__), which a TP wheel bakes as "TRAFFICPEAK_".
    monkeypatch.setattr(mcp_env, "__env_prefix__", "TRAFFICPEAK_")
    with pytest.raises(ValueError) as excinfo:
        HydrolixConfig()
    msg = str(excinfo.value)
    assert "TRAFFICPEAK_URL" in msg
    assert "HYDROLIX_URL" not in msg


def test_resolution_does_not_mutate_environment(brand_env):
    # Read-time coalesce, not projection: constructing config with only TP vars
    # must leave os.environ untouched (no generated HYDROLIX_* entries).
    brand_env["TRAFFICPEAK_URL"] = "https://tp.example.live"
    HydrolixConfig()
    assert "HYDROLIX_URL" not in os.environ
    assert brand_getenv("HYDROLIX_URL") == "https://tp.example.live"  # coalesced read


def test_deprecated_alias_suffix_not_mirrored_from_trafficpeak(brand_env):
    # TRAFFICPEAK_* mirrors only the modern scheme; a deprecated-alias suffix
    # (e.g. HOST) is NOT read from TRAFFICPEAK_HOST -- the host comes from the URL.
    brand_env["TRAFFICPEAK_URL"] = "https://tp.example.live"
    brand_env["TRAFFICPEAK_HOST"] = "should-not-map"
    config = HydrolixConfig()
    assert config.host == "tp.example.live"  # from TRAFFICPEAK_URL, not TRAFFICPEAK_HOST
    assert brand_getenv("HYDROLIX_HOST") is None  # deprecated suffix not mirrored
    assert mcp_env._DEPRECATED_SUFFIXES  # guard: suffix set is non-empty


# ==========================================================================  #
# Build-time brand flag + metadata + baked runtime identifier                 #
# ==========================================================================  #
def _build(brand: str, out_dir: Path) -> None:
    env = {**os.environ, "MCP_BRAND": brand}
    if brand == "hydrolix":
        cmd = ["uv", "build", "--out-dir", str(out_dir)]
    else:
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "brand_build.py"),
            "--out-dir",
            str(out_dir),
        ]
    subprocess.run(
        cmd, cwd=REPO_ROOT, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )


@pytest.fixture(scope="session")
def hydrolix_wheel(tmp_path_factory):
    d = tmp_path_factory.mktemp("hdx")
    _build("hydrolix", d)
    return next(d.glob("mcp_hydrolix-*.whl"))


@pytest.fixture(scope="session")
def trafficpeak_wheel(tmp_path_factory):
    d = tmp_path_factory.mktemp("tp")
    _build("trafficpeak", d)
    return next(d.glob("mcp_trafficpeak-*.whl"))


def _wheel_text(wheel: Path, member_suffix: str) -> str:
    with zipfile.ZipFile(wheel) as z:
        name = next(n for n in z.namelist() if n.endswith(member_suffix))
        return z.read(name).decode("utf-8")


def _metadata(wheel: Path):
    return email.message_from_string(_wheel_text(wheel, ".dist-info/METADATA"))


@pytest.mark.brand_build
def test_default_build_produces_the_hydrolix_wheel(hydrolix_wheel):
    assert hydrolix_wheel.name.startswith("mcp_hydrolix-")
    assert _metadata(hydrolix_wheel)["Name"] == "mcp-hydrolix"
    assert "mcp-hydrolix = mcp_hydrolix.main:main" in _wheel_text(
        hydrolix_wheel, ".dist-info/entry_points.txt"
    )


@pytest.mark.brand_build
def test_trafficpeak_build_via_env_var_produces_the_tp_wheel(trafficpeak_wheel, hydrolix_wheel):
    assert trafficpeak_wheel.name.startswith("mcp_trafficpeak-")
    md = _metadata(trafficpeak_wheel)
    assert md["Name"] == "mcp-trafficpeak"
    assert "mcp-trafficpeak = mcp_hydrolix.main:main" in _wheel_text(
        trafficpeak_wheel, ".dist-info/entry_points.txt"
    )
    assert md["Version"] == _metadata(hydrolix_wheel)["Version"]


def test_invalid_mcp_brand_value_fails_fast(monkeypatch):
    monkeypatch.setenv("MCP_BRAND", "foo")
    with pytest.raises(ValueError) as exc:
        hatch_build.selected_brand()
    msg = str(exc.value)
    assert "MCP_BRAND" in msg and "hydrolix" in msg and "trafficpeak" in msg


@pytest.mark.brand_build
def test_pip_show_on_tp_wheel_has_no_hydrolix_string(trafficpeak_wheel):
    md = _metadata(trafficpeak_wheel)
    # Brand-sensitive fields must be hydrolix-free. The Source project-URL
    # intentionally points at the sibling repo under the hydrolix org (accepted
    # exemption for repository-pointing fields), so it is excluded here.
    for field in ("Name", "Summary", "Author", "Author-email", "License"):
        assert "hydrolix" not in (md.get(field, "") or "").lower(), field
    home = [u for u in md.get_all("Project-URL", []) if u.lower().startswith("home")]
    assert home and "hydrolix" not in home[0].lower()


@pytest.mark.brand_build
def test_pip_show_on_hydrolix_wheel_is_unchanged(hydrolix_wheel):
    md = _metadata(hydrolix_wheel)
    assert md["Name"] == "mcp-hydrolix"
    assert md["Summary"] == "An MCP server for Hydrolix."
    blob = "\n".join(f"{k}: {v}" for k, v in md.items())
    assert "trafficpeak" not in blob.lower()


@pytest.mark.brand_build
def test_long_description_is_generated_by_the_brand_filter_from_this_repos_readme(hydrolix_wheel):
    # Hydrolix mode: identity transform -> README verbatim.
    assert _metadata(hydrolix_wheel).get_payload().strip() == README.strip()


@pytest.mark.brand_build
def test_long_description_tokens_are_rebranded_for_trafficpeak_builds(trafficpeak_wheel):
    desc = _metadata(trafficpeak_wheel).get_payload()
    assert desc.strip() == hatch_build.rebrand_text(README, "trafficpeak").strip()
    assert "mcp-hydrolix" not in desc
    assert "HYDROLIX_" not in desc
    assert "mcp-trafficpeak" in desc


def test_readme_rebrand_filter_is_identity_for_hydrolix():
    assert hatch_build.rebrand_text(README, "hydrolix") == README


def test_trafficpeak_long_description_prose_has_zero_hydrolix():
    # Prose rule: a mcp-trafficpeak build's customer-facing long description MUST
    # NOT mention Hydrolix at all (case-insensitive) -- lowercase host/url/config
    # tokens and shields badges included -- EXCEPT the GitHub-org identity
    # namespace (io.github.hydrolix / github.com/hydrolix), a structured
    # ownership identity that names the owning org, not brand prose.
    desc = hatch_build.rebrand_text(README, "trafficpeak")
    # The exempt org identity survives, but its package segment still rebrands.
    assert "io.github.hydrolix/mcp-trafficpeak" in desc
    stripped = desc.replace("io.github.hydrolix", "").replace("github.com/hydrolix", "")
    assert "hydrolix" not in stripped.lower()


@pytest.mark.brand_build
def test_brand_module_baked_into_each_wheel(hydrolix_wheel, trafficpeak_wheel):
    assert '__dist_name__ = "mcp-hydrolix"' in _wheel_text(hydrolix_wheel, "mcp_hydrolix/_brand.py")
    tp = _wheel_text(trafficpeak_wheel, "mcp_hydrolix/_brand.py")
    assert '__brand__ = "trafficpeak"' in tp
    assert '__dist_name__ = "mcp-trafficpeak"' in tp


def _run_with_brand(brand: str, snippet: str) -> str:
    """Exec ``snippet`` in a subprocess with _brand.py patched to ``brand``.

    Only ``_brand.py`` differs between the two wheels, so patching it is
    equivalent to running from a wheel built for ``brand`` -- without a venv.
    """
    code = (
        "import mcp_hydrolix._brand as b\n"
        f"b.__brand__ = {brand!r}\n"
        f"b.__dist_name__ = 'mcp-{brand}'\n"
        "import os\n"
        "os.environ['HYDROLIX_URL'] = 'https://example.invalid'\n" + snippet
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            k: v for k, v in os.environ.items() if not k.startswith(("HYDROLIX_", "TRAFFICPEAK_"))
        },
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_brand_identifier_in_startup_log_reflects_baked_constant():
    out = _run_with_brand(
        "trafficpeak",
        "from mcp_hydrolix.mcp_server import startup_banner\nprint(startup_banner())\n",
    )
    assert "trafficpeak" in out and "mcp-hydrolix" not in out


def test_brand_identifier_in_outbound_user_agent_reflects_baked_constant():
    out = _run_with_brand(
        "trafficpeak", "from mcp_hydrolix.mcp_server import USER_AGENT\nprint(USER_AGENT)\n"
    )
    assert out.strip().startswith("mcp-trafficpeak/")


def test_renaming_the_launcher_does_not_change_the_reported_brand():
    out = _run_with_brand(
        "trafficpeak",
        "import sys\nsys.argv[0] = 'mcp-hydrolix'\n"
        "from mcp_hydrolix.mcp_server import startup_banner, USER_AGENT\n"
        "print(startup_banner()); print(USER_AGENT)\n",
    )
    assert "trafficpeak" in out and "mcp-hydrolix" not in out


def test_fastmcp_server_name_reflects_the_baked_distribution_name():
    out = _run_with_brand(
        "trafficpeak", "from mcp_hydrolix.mcp_server import mcp\nprint(mcp.name)\n"
    )
    assert out.strip() == "mcp-trafficpeak"


def test_admin_comment_user_token_reflects_the_baked_distribution_name():
    out = _run_with_brand(
        "trafficpeak",
        "from mcp_hydrolix.mcp_server import HDX_ADMIN_COMMENT\nprint(HDX_ADMIN_COMMENT)\n",
    )
    assert "User: mcp-trafficpeak" in out and "mcp-hydrolix" not in out


def test_no_customer_visible_output_of_a_trafficpeak_wheel_contains_the_hydrolix_distribution_name():
    out = _run_with_brand(
        "trafficpeak",
        "from mcp_hydrolix.mcp_server import startup_banner, USER_AGENT, HDX_ADMIN_COMMENT, mcp\n"
        "print(startup_banner()); print(USER_AGENT); print(HDX_ADMIN_COMMENT); print(mcp.name)\n",
    )
    assert "mcp-hydrolix" not in out


# ==========================================================================  #
# Existing Hydrolix surface preserved + docs are Hydrolix-only                #
# ==========================================================================  #
def test_pre_change_customer_config_still_works(brand_env):
    brand_env["HYDROLIX_URL"] = "https://mycluster.hydrolix.live"
    config = HydrolixConfig()
    assert config.host == "mycluster.hydrolix.live"
    assert config.secure is True


def test_python_import_path_is_unchanged():
    import mcp_hydrolix
    import mcp_hydrolix.mcp_server  # noqa: F401

    assert mcp_hydrolix.__name__ == "mcp_hydrolix"


def test_readme_does_not_mention_trafficpeak():
    assert "trafficpeak" not in README.lower()


def test_internal_engineering_docs_may_mention_both_brands():
    # The capability spec is the durable home for this branding contract; the
    # proposal.md that originally carried it moves under changes/archive/ once
    # the change is archived, so assert against the synced spec instead.
    spec = REPO_ROOT / "openspec" / "specs" / "mcp-server-branding" / "spec.md"
    text = spec.read_text(encoding="utf-8").lower()
    assert "trafficpeak" in text  # allowed (and expected) in internal docs


# ==========================================================================  #
# brands.toml is the single source of truth                                   #
# ==========================================================================  #
def test_exempt_org_tokens_appear_verbatim_in_readme():
    # The rebrand filter protects these via case-sensitive replace; a token in
    # brands.toml that doesn't match README byte-for-byte silently protects
    # nothing. Guard the config against the doc.
    for token in hatch_build._EXEMPT_ORG_TOKENS:
        assert token in README, f"exempt token {token!r} not found verbatim in README.md"


def test_baked_env_constants_match_brands_toml():
    # The runtime _brand.py the hook bakes must reflect brands.toml exactly, for
    # every brand (own prefix + the shared precedence order).
    precedence = tuple(hatch_build.BRANDS[b]["env_prefix"] for b in hatch_build._PRECEDENCE)
    for brand, cfg in hatch_build.BRANDS.items():
        src = hatch_build.brand_module_source(brand)
        assert f'__env_prefix__ = "{cfg["env_prefix"]}"' in src
        assert f"__env_prefix_precedence__ = {precedence!r}" in src
        assert f'__dist_name__ = "{cfg["dist_name"]}"' in src


def test_no_brand_table_outside_brands_toml():
    # Single-source guard: the previously-duplicated per-brand tables must be
    # gone from the other toolchains (they now read brands.toml).
    build_sh = (REPO_ROOT / "mcpb" / "build.sh").read_text()
    assert "brand_meta.py" in build_sh and 'DIST_NAME="mcp-' not in build_sh
    env_py = (REPO_ROOT / "mcp_hydrolix" / "mcp_env.py").read_text()
    assert 'TRAFFICPEAK_PREFIX = "TRAFFICPEAK_"' not in env_py
    publish = (REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text()
    assert "for brand in hydrolix trafficpeak" not in publish


@pytest.mark.brand_build
def test_sdist_is_self_sufficient_for_a_brand_build(tmp_path):
    # brands.toml must ship in the sdist, else a wheel-from-sdist / source build
    # fails inside the metadata hook. Build an sdist, extract it, and build a
    # TrafficPeak wheel purely from the extracted tree.
    import subprocess
    import tarfile

    out = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(out)],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    sdist = next(out.glob("mcp_hydrolix-*.tar.gz"))
    with tarfile.open(sdist) as t:
        t.extractall(tmp_path / "x")
    root = next((tmp_path / "x").glob("mcp_hydrolix-*"))
    assert (root / "brands.toml").exists(), "brands.toml missing from sdist"
    wheels = root / "w"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "brand_build.py"),
            "--wheel",
            "--out-dir",
            str(wheels),
        ],
        cwd=root,
        env={**os.environ, "MCP_BRAND": "trafficpeak"},
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    assert list(wheels.glob("mcp_trafficpeak-*.whl")), "TP wheel not built from extracted sdist"


# ==========================================================================  #
# mcpb bundle is brand-parameterized                                          #
# ==========================================================================  #
@pytest.fixture
def restore_mcpb_render():
    """Snapshot the generated mcpb files and restore them after the test.

    build.sh renders to the fixed mcpb/manifest.json / mcpb/pyproject.toml, so
    tests that render a non-Hydrolix brand must restore the committed content to
    keep the working tree clean.
    """
    generated = [REPO_ROOT / "mcpb" / "manifest.json", REPO_ROOT / "mcpb" / "pyproject.toml"]
    saved = {p: p.read_bytes() for p in generated if p.exists()}
    try:
        yield
    finally:
        for p, data in saved.items():
            p.write_bytes(data)


def _render_mcpb(brand: str) -> str:
    subprocess.run(
        ["bash", "mcpb/build.sh"],
        cwd=REPO_ROOT,
        env={**os.environ, "MCP_BRAND": brand, "MCPB_RENDER_ONLY": "1"},
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return (REPO_ROOT / "mcpb" / "manifest.json").read_text(encoding="utf-8")


@pytest.mark.brand_build
def test_tp_mode_mcpb_build_emits_a_tp_branded_bundle(restore_mcpb_render):
    import json

    manifest = json.loads(_render_mcpb("trafficpeak"))
    assert manifest["name"] == "mcp-trafficpeak"
    # No hydrolix anywhere EXCEPT the repository pointer (accepted exemption).
    for key, value in manifest.items():
        if key == "repository":
            continue
        assert "hydrolix" not in json.dumps(value).lower(), key
    assert "TRAFFICPEAK_URL" in manifest["server"]["mcp_config"]["env"]
    assert any("TrafficPeak" in cfg.get("title", "") for cfg in manifest["user_config"].values())


@pytest.mark.brand_build
def test_default_mode_mcpb_build_emits_the_hydrolix_bundle_unchanged(restore_mcpb_render):
    import json

    manifest = json.loads(_render_mcpb("hydrolix"))
    assert manifest["name"] == "mcp-hydrolix"
    assert "trafficpeak" not in json.dumps(manifest).lower()
    assert "HYDROLIX_URL" in manifest["server"]["mcp_config"]["env"]
