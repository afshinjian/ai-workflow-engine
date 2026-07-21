"""Independent, fresh ORCH-002 reviewer CLI/library probes (not copied from implementation tests).

Probes: inspect v1/v2, prompt --no-store v2, state v2 in isolated storage, a v2
configuration failure, contradictory ContractEnvelopeV2 construction (direct and via
registry dispatch), FORCE_COLOR stdout purity, an invalid --contract-version fail-closed
check, a safe commit writable-gate refusal (asserts HEAD unchanged), and SchemaRegistry
duplicate-registration / unknown-name / unknown-version rejection.
"""

import json
import os
import subprocess
import sys

REPO = "/tmp/claude-1000/-home-afshin-jian-ai-workflow-engine/d800ef63-4afd-4564-9e97-3737d3d0fb75/scratchpad/orch002_probe/repo"
CFG = "/tmp/claude-1000/-home-afshin-jian-ai-workflow-engine/d800ef63-4afd-4564-9e97-3737d3d0fb75/scratchpad/orch002_probe/probe-config.yaml"
HOME_DIR = "/tmp/claude-1000/-home-afshin-jian-ai-workflow-engine/d800ef63-4afd-4564-9e97-3737d3d0fb75/scratchpad/orch002_probe/isolated-home"

ok = True


def check(label: str, cond: bool) -> None:
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{status}] {label}")


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "ai_workflow_engine", *args],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )


def main() -> None:
    os.environ["HOME"] = HOME_DIR
    os.makedirs(HOME_DIR, exist_ok=True)

    # Probe 1: inspect v1 (default) and v2
    r1 = run(["inspect", "--config", CFG, "--output", "json"])
    p1 = json.loads(r1.stdout)
    check("inspect v1: no contract_version envelope key", "contract_version" not in p1)
    check("inspect v1: exit 0", r1.returncode == 0)

    r1b = run(["--contract-version", "2", "inspect", "--config", CFG, "--output", "json"])
    p1b = json.loads(r1b.stdout)
    check(
        "inspect v2: exactly the 6 envelope keys",
        list(p1b) == ["contract_version", "command", "ok", "data", "error", "warnings"],
    )
    check("inspect v2: ok=true, error=None, data present", p1b["ok"] is True and p1b["error"] is None and p1b["data"])

    # Probe 2: prompt --no-store v2, nothing written under isolated $HOME
    r2 = run(
        [
            "--contract-version",
            "2",
            "prompt",
            "plan-review",
            "--config",
            CFG,
            "--task-id",
            "T-1",
            "--no-store",
            "--output",
            "json",
        ]
    )
    p2 = json.loads(r2.stdout)
    check("prompt --no-store v2: ok=true", p2["ok"] is True)
    check("prompt --no-store v2: data.stored == false", p2["data"]["stored"] is False)
    written = [f for _, _, files in os.walk(HOME_DIR) for f in files]
    check("prompt --no-store: nothing written under isolated $HOME", written == [])

    # Probe 3: state v2 in isolated storage (no prior events -> next_stage plan-review)
    r3 = run(["--contract-version", "2", "state", "next", "--config", CFG, "--task-id", "T-1", "--output", "json"])
    p3 = json.loads(r3.stdout)
    check("state next v2: ok=true, next_stage=plan-review", p3["ok"] is True and p3["data"]["next_stage"] == "plan-review")

    # Probe 4: v2 configuration failure
    r4 = run(["--contract-version", "2", "check-handover", "--config", "/no/such/config.yaml", "--output", "json"])
    p4 = json.loads(r4.stdout)
    check("v2 config failure: exit 1", r4.returncode == 1)
    check("v2 config failure: ok=false, data=None", p4["ok"] is False and p4["data"] is None)
    check("v2 config failure: error.code == InvalidConfigurationError", p4["error"]["code"] == "InvalidConfigurationError")

    # Probe 5: contradictory ContractEnvelopeV2 construction (direct + registry dispatch)
    from pydantic import ValidationError

    from ai_workflow_engine.schema.contract import (
        CLI_CONTRACT_REGISTRY,
        CLI_CONTRACT_SCHEMA_NAME,
        ContractEnvelopeV2,
        ContractErrorV2,
    )

    def rejects(build) -> bool:
        try:
            build()
            return False
        except ValidationError:
            return True

    check(
        "ContractEnvelopeV2 rejects ok=true/data=None",
        rejects(lambda: ContractEnvelopeV2(command="x", ok=True, data=None, error=None)),
    )
    check(
        "ContractEnvelopeV2 rejects ok=false/data-present",
        rejects(lambda: ContractEnvelopeV2(command="x", ok=False, data={"a": 1}, error=None)),
    )
    check(
        "ContractEnvelopeV2 rejects ok=true-with-error",
        rejects(
            lambda: ContractEnvelopeV2(
                command="x", ok=True, data={"a": 1}, error=ContractErrorV2(code="C", message="m")
            )
        ),
    )
    check(
        "registry dispatch rejects ok=false/error=None (external-input path)",
        rejects(
            lambda: CLI_CONTRACT_REGISTRY.dispatch(
                CLI_CONTRACT_SCHEMA_NAME,
                "2.0.0",
                {
                    "contract_version": "2.0.0",
                    "command": "x",
                    "ok": False,
                    "data": None,
                    "error": None,
                    "warnings": [],
                },
            )
        ),
    )

    # Probe 6: FORCE_COLOR stdout purity
    r6 = run(
        ["--contract-version", "2", "inspect", "--config", CFG, "--output", "json"],
        env={"FORCE_COLOR": "3"},
    )
    check("FORCE_COLOR: no ESC byte in stdout", "\x1b" not in r6.stdout)
    decoder = json.JSONDecoder()
    _, end = decoder.raw_decode(r6.stdout.strip())
    check("FORCE_COLOR: exactly one JSON document", end == len(r6.stdout.strip()))

    # Probe 7: invalid --contract-version fails closed, before contract selection
    r7 = run(["--contract-version", "3", "inspect", "--config", CFG, "--output", "json"])
    check("invalid contract-version: exit 2", r7.returncode == 2)
    check("invalid contract-version: zero stdout bytes", r7.stdout == "")
    check("invalid contract-version: stderr mentions supported versions", "supported versions" in r7.stderr)

    # Probe 8: safe writable-gate refusal (commit, wrong HEAD) -- must perform no write
    head_before = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    approval_path = "/tmp/orch002_review_bad_approval.yaml"
    with open(approval_path, "w") as fh:
        fh.write(
            "kind: commit\n"
            "task_id: T-1\n"
            "branch: main\n"
            f"head: {'f' * 40}\n"
            "allowed_paths: [docs/PROJECT_STATE.md]\n"
            'message: "review probe"\n'
            "approved_by: reviewer@example.invalid\n"
        )
    r8 = run(
        ["--contract-version", "2", "commit", "--config", CFG, "--approval", approval_path, "--output", "json"]
    )
    p8 = json.loads(r8.stdout)
    head_after = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    check("writable-gate refusal: exit 1, ok=false", r8.returncode == 1 and p8["ok"] is False)
    check("writable-gate refusal: HEAD unchanged (no write performed)", head_before == head_after)

    # Probe 9: SchemaRegistry duplicate/unknown rejection
    from pydantic import BaseModel

    from ai_workflow_engine.exceptions import UnknownSchemaNameError, UnsupportedSchemaVersionError
    from ai_workflow_engine.schema.registry import SchemaRegistry

    class Widget(BaseModel):
        x: int

    reg = SchemaRegistry()
    reg.register("w", "1.0.0", Widget)
    check(
        "duplicate registration rejected",
        rejects_exc(lambda: reg.register("w", "1.0.0", Widget), ValueError),
    )
    check(
        "unknown schema name rejected",
        rejects_exc(lambda: reg.get("nope", "1.0.0"), UnknownSchemaNameError),
    )
    check(
        "unknown schema version rejected",
        rejects_exc(lambda: reg.get("w", "9.9.9"), UnsupportedSchemaVersionError),
    )

    print()
    print("ALL_PROBES_PASS" if ok else "SOME_PROBES_FAILED")
    sys.exit(0 if ok else 1)


def rejects_exc(build, exc_type) -> bool:
    try:
        build()
        return False
    except exc_type:
        return True


if __name__ == "__main__":
    main()
