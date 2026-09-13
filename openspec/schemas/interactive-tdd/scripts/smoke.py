"""Exercise the portable schema through the installed CLI in a temporary project."""

import json
import os
from pathlib import Path
import subprocess
import tempfile


SOURCE = Path(__file__).resolve().parent.parent


def run(root: Path, env: dict[str, str], *args: str, code: int = 0) -> str:
    result = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True)
    if result.returncode != code:
        raise AssertionError(
            f"{args}: expected exit {code}, got {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout + (result.stderr if code else "")


def cli(root: Path, env: dict[str, str], *args: str) -> dict:
    return json.loads(run(root, env, "openspec", *args, "--json"))


def write(root: Path, name: str, content: str) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def planning(change: Path) -> None:
    write(
        change,
        "proposal.md",
        """# Proposal
## Why
Callers need an eligibility decision.
## What Changes
Expose eligibility through a public function.
## Capabilities
### New
- `eligibility` - Determine eligibility.
### Modified
- *none*
## Impact
A new public function.
""",
    )
    write(
        change,
        "explore.md",
        """# Exploration
## Decisions
### Decision: eligibility-rule
- Question: Which ages qualify?
- Answer: Fixture contract: age 18 and above; this is synthetic test data.
- Rationale: Exercise an observable boundary.
- Affects: specs/eligibility/spec.md Requirement: Eligibility
""",
    )
    write(
        change,
        "specs/eligibility/spec.md",
        """## ADDED Requirements
### Requirement: Eligibility
The function SHALL return true for ages at least 18.
<!-- settle: explore/eligibility-rule -->
#### Scenario: Adult Qualifies
- **WHEN** eligibility is requested for age 18
- **THEN** the result is true
""",
    )
    write(
        change,
        "design.md",
        """# Design
## Execution Context
Target code root and verification directory: temporary smoke project root.
Runner: uv run --no-project python -m unittest test_policy
## Decisions
### Decision: public-function
- Choice: A pure eligible(age) function.
- Why: explore/eligibility-rule
- Alternatives: A class is unnecessary.
- Binding: eligibility/eligibility
## Testing Seams
### Seam: eligibility
- Interface: eligible(age)
- Agreement: Synthetic fixture contract, not a real user approval.
- Scenarios: eligibility/eligibility/adult-qualifies
""",
    )
    write(
        change,
        "tasks.md",
        "# Tasks\n"
        "- [ ] 1.1 Implement eligibility [implements: eligibility/eligibility, meta/tests] "
        "[mode: tdd] [scenarios: eligibility/eligibility/adult-qualifies] "
        "[seam: eligibility] - verify: "
        "`uv run --no-project python -m unittest test_policy` passes\n"
        "- [ ] 1.2 Complete review [implements: meta/tooling] [mode: check] "
        "[scenarios: none] [seam: none] - verify: "
        "`uv run --no-project python -m unittest test_policy` passes; "
        "review.md records no unresolved blocking findings\n",
    )


def exercise(root: Path, env: dict[str, str]) -> None:
    installer = str(SOURCE / "scripts" / "install.py")
    run(root, env, "uv", "run", "--no-project", "python", installer)
    run(root, env, "uv", "run", "--no-project", "python", installer)
    installed = Path(env["XDG_DATA_HOME"]) / "openspec/schemas/interactive-tdd"
    assert cli(root, env, "schema", "which", "interactive-tdd")["source"] == "user"
    assert cli(root, env, "schema", "validate", "interactive-tdd")["valid"]
    (installed / "README.md").write_text("A user's local modification.\n")
    refusal = run(root, env, "uv", "run", "--no-project", "python", installer, code=1)
    assert "Refusing to overwrite" in refusal
    assert (installed / "README.md").read_text() == "A user's local modification.\n"
    print("PASS: user installation, idempotence, resolution, overwrite protection")

    cli(root, env, "new", "change", "eligibility", "--schema", "interactive-tdd")
    initial = cli(root, env, "instructions", "apply", "--change", "eligibility")
    assert initial["state"] == "blocked"
    change = root / "openspec/changes/eligibility"
    planning(change)
    for artifact in ("proposal", "explore", "specs", "design", "tasks", "review"):
        instructions = cli(root, env, "instructions", artifact, "--change", "eligibility")
        assert instructions["instruction"] and instructions["template"]
    status = cli(root, env, "status", "--change", "eligibility")
    assert "review" not in status["applyRequires"]
    ready = cli(root, env, "instructions", "apply", "--change", "eligibility")
    assert ready["state"] == "ready", ready
    assert ready["progress"]["total"] == 2, ready
    assert not (change / "review.md").exists()
    run(root, env, "openspec", "validate", "eligibility", "--strict")
    print("PASS: planning graph, instructions, apply blocking/readiness, delta validation")

    write(root, "policy.py", "def eligible(age):\n    return False\n")
    write(
        root,
        "test_policy.py",
        """import unittest
from policy import eligible

class EligibilityTest(unittest.TestCase):
    def test_adult_qualifies(self):
        self.assertTrue(eligible(18))
""",
    )
    command = ("uv", "run", "--no-project", "python", "-m", "unittest", "test_policy")
    red = run(root, env, *command, code=1)
    assert "AssertionError: False is not true" in red
    still_open = cli(root, env, "instructions", "apply", "--change", "eligibility")
    assert still_open["progress"]["complete"] == 0
    write(root, "policy.py", "def eligible(age):\n    return age >= 18\n")
    run(root, env, *command)
    write(
        change,
        "evidence.md",
        """# Evidence
## Task 1.1
- Scenario: eligibility/eligibility/adult-qualifies
- Seam and test: eligibility; EligibilityTest.test_adult_qualifies
- Working directory: temporary smoke project root
- Red: uv run --no-project python -m unittest test_policy; exit 1; False is not true
- Green: uv run --no-project python -m unittest test_policy; exit 0
- Verify: same command; passed
- Limitations: synthetic CLI fixture, not a full agent evaluation
""",
    )
    tasks = change / "tasks.md"
    tasks.write_text(tasks.read_text().replace("[ ]", "[x]", 1))
    pending_review = cli(root, env, "instructions", "apply", "--change", "eligibility")
    assert pending_review["state"] == "ready", pending_review
    assert pending_review["progress"]["remaining"] == 1
    assert not (change / "review.md").exists()
    review = cli(root, env, "instructions", "review", "--change", "eligibility")
    assert "POST-IMPLEMENTATION ONLY" in review["instruction"]
    write(change, "review.md", "# Review\nSynthetic completion fixture, not a real review.\n")
    tasks.write_text(tasks.read_text().replace("[ ]", "[x]"))
    complete = cli(root, env, "instructions", "apply", "--change", "eligibility")
    assert complete["state"] == "all_done", complete
    print("PASS: real red/green cycle, task progress, final review task before all_done")

    cli(root, env, "new", "change", "docs-only", "--schema", "interactive-tdd")
    docs = root / "openspec/changes/docs-only"
    metadata = docs / ".openspec.yaml"
    metadata.write_text(metadata.read_text() + "skip_specs: true\n")
    write(docs, "proposal.md", "# Proposal\nDocumentation only; no capability deltas.\n")
    write(docs, "explore.md", "# Exploration\nScope is the existing documentation.\n")
    write(docs, "design.md", "# Design\nSeams not applicable; direct document validation.\n")
    write(
        docs,
        "tasks.md",
        "# Tasks\n"
        "- [ ] 1.1 Fix documentation [implements: meta/docs] [mode: check] "
        "[scenarios: none] [seam: none] - verify: `git diff --check` passes\n"
        "  - Reason: Behavior-neutral documentation edit.\n",
    )
    docs_status = cli(root, env, "status", "--change", "docs-only")
    spec_status = next(a for a in docs_status["artifacts"] if a["id"] == "specs")
    assert spec_status["status"] == "skipped", docs_status
    docs_apply = cli(root, env, "instructions", "apply", "--change", "docs-only")
    assert docs_apply["state"] == "ready", docs_apply
    print("PASS: behavior-neutral change skips specs and can apply")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="openspec-tdd-smoke-") as temp:
        root = Path(temp)
        env = dict(os.environ)
        env.update(
            {
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
                "OPENSPEC_TELEMETRY": "0",
            }
        )
        write(root, "openspec/config.yaml", "schema: interactive-tdd\n")
        exercise(root, env)
    print("PASS: all smoke checks (temporary project removed)")


if __name__ == "__main__":
    main()
