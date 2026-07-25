"""
Pulse Orchestrator — Repair Runner

Coordinates the repair attempt cycle:
  1. Ask the Repair Agent to generate a fix
  2. Spin up a Docker sandbox
  3. Apply the patch
  4. Run tests
  5. If tests pass → success! If not → retry with error feedback
  6. After MAX_ATTEMPTS failures → mark as unfixable

This module ties together the repair_agent (LLM) and docker_runner (sandbox).
It emits Socket.io events at each step so the dashboard can show progress.
"""

import time
from typing import Optional

from app.agents import repair_agent
from app.sandbox.docker_runner import docker_runner
from app.models.agent_models import (
    Finding,
    RepairResult,
    RepairStatus,
)
from app.ws.socket_server import emit_event
from app.utils.logger import setup_logger

logger = setup_logger("pulse.repair")

# Maximum number of repair attempts per finding
MAX_ATTEMPTS = 3

# Default test commands by project type
DEFAULT_TEST_COMMANDS = {
    "python": "cd /workspace && python -m pytest -x -q 2>&1",
    "node": "cd /workspace && npm test 2>&1",
    "default": "echo 'No test command configured — assuming pass' && exit 0",
}


def _detect_test_command(changed_files: list[str]) -> str:
    """
    Auto-detect the test command based on changed files.

    Simple heuristic:
    - If any .py files → pytest
    - If any .js/.ts files → npm test
    - Otherwise → default (pass)
    """
    extensions = {f.rsplit(".", 1)[-1].lower() for f in changed_files if "." in f}

    if extensions & {"py"}:
        return DEFAULT_TEST_COMMANDS["python"]
    elif extensions & {"js", "ts", "jsx", "tsx"}:
        return DEFAULT_TEST_COMMANDS["node"]
    else:
        return DEFAULT_TEST_COMMANDS["default"]


async def run_repair(
    finding: Finding,
    finding_index: int,
    diff: str,
    changed_files: list[str],
    project_path: Optional[str] = None,
    test_command: Optional[str] = None,
) -> RepairResult:
    """
    Run the full repair cycle for a single critical finding.

    Args:
        finding: The critical finding to fix
        finding_index: Index of the finding in the results
        diff: The original diff containing the issue
        changed_files: List of changed file paths
        project_path: Optional path to the project root (for Docker copy)
        test_command: Optional test command override

    Returns:
        RepairResult with the patch, test output, and status
    """
    start_time = time.time()

    # Auto-detect test command if not provided
    if not test_command:
        test_command = _detect_test_command(changed_files)

    logger.info(
        f"Starting repair for finding '{finding.title}' "
        f"in {finding.file}:{finding.line}"
    )

    # ── Emit: repair started ──
    await emit_event("repair_started", {
        "finding_index": finding_index,
        "finding_title": finding.title,
        "finding_file": finding.file,
        "max_attempts": MAX_ATTEMPTS,
    })

    previous_errors: list[str] = []
    last_patch = ""
    last_explanation = ""
    last_confidence = 0.0

    # Check if Docker is available
    docker_available = await docker_runner.is_available()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info(f"Repair attempt {attempt}/{MAX_ATTEMPTS}...")

        # ── Emit: attempt started ──
        await emit_event("repair_attempt", {
            "finding_index": finding_index,
            "attempt": attempt,
            "max_attempts": MAX_ATTEMPTS,
            "status": "generating_fix",
        })

        # Step 1: Generate a fix patch
        fix_result = await repair_agent.generate_fix(
            finding=finding,
            diff=diff,
            previous_errors=previous_errors if previous_errors else None,
        )

        last_patch = fix_result["patch"]
        last_explanation = fix_result["explanation"]
        last_confidence = fix_result["confidence"]

        if not last_patch or last_confidence == 0.0:
            logger.warning(f"Repair Agent returned empty/zero-confidence patch on attempt {attempt}")
            previous_errors.append(f"Repair Agent returned no viable patch: {last_explanation}")
            continue

        # ── Emit: patch generated ──
        await emit_event("repair_attempt", {
            "finding_index": finding_index,
            "attempt": attempt,
            "max_attempts": MAX_ATTEMPTS,
            "status": "testing_fix",
            "patch_length": len(last_patch),
            "confidence": last_confidence,
        })

        # Step 2: Test the patch in Docker sandbox (if available)
        if docker_available:
            try:
                container_id = await docker_runner.create_sandbox(project_path)

                # Apply the patch
                patch_applied = await docker_runner.apply_patch(container_id, last_patch)
                if not patch_applied:
                    previous_errors.append("Failed to apply patch in sandbox (git apply failed)")
                    await docker_runner.cleanup(container_id)
                    continue

                # Run tests
                test_result = await docker_runner.run_tests(container_id, test_command)

                # Cleanup
                await docker_runner.cleanup(container_id)

                if test_result.passed:
                    # ── SUCCESS ──
                    duration = time.time() - start_time
                    logger.info(
                        f"Repair SUCCEEDED on attempt {attempt} — "
                        f"tests passed in {test_result.duration_seconds:.1f}s"
                    )

                    result = RepairResult(
                        finding_index=finding_index,
                        finding_title=finding.title,
                        finding_file=finding.file,
                        patch=last_patch,
                        explanation=last_explanation,
                        test_output=test_result.stdout[:5000],
                        tests_passed=True,
                        attempts_taken=attempt,
                        status=RepairStatus.SUCCEEDED,
                        confidence=last_confidence,
                        duration_seconds=round(duration, 2),
                    )

                    await emit_event("repair_succeeded", {
                        "finding_index": finding_index,
                        "finding_title": finding.title,
                        "attempt": attempt,
                        "patch": last_patch,
                        "explanation": last_explanation,
                        "test_output": test_result.stdout[:2000],
                        "confidence": last_confidence,
                        "duration": round(duration, 2),
                    })

                    return result
                else:
                    # Tests failed — collect error for next attempt
                    error_output = test_result.stdout or test_result.stderr
                    previous_errors.append(error_output[:3000])
                    logger.warning(
                        f"Repair attempt {attempt} failed — "
                        f"tests exited with code {test_result.exit_code}"
                    )

            except Exception as e:
                logger.error(f"Sandbox error on attempt {attempt}: {e}")
                previous_errors.append(f"Sandbox error: {str(e)}")
                try:
                    await docker_runner.cleanup(container_id)
                except Exception:
                    pass
        else:
            # Docker not available — accept the fix on confidence alone
            logger.warning(
                "Docker not available — accepting fix based on LLM confidence only"
            )
            duration = time.time() - start_time

            result = RepairResult(
                finding_index=finding_index,
                finding_title=finding.title,
                finding_file=finding.file,
                patch=last_patch,
                explanation=last_explanation,
                test_output="Docker not available — fix not verified by tests",
                tests_passed=False,
                attempts_taken=attempt,
                status=RepairStatus.SUCCEEDED,
                confidence=last_confidence,
                duration_seconds=round(duration, 2),
            )

            await emit_event("repair_succeeded", {
                "finding_index": finding_index,
                "finding_title": finding.title,
                "attempt": attempt,
                "patch": last_patch,
                "explanation": last_explanation,
                "test_output": "Docker not available — fix based on LLM confidence",
                "confidence": last_confidence,
                "duration": round(duration, 2),
                "docker_verified": False,
            })

            return result

    # ── ALL ATTEMPTS EXHAUSTED ──
    duration = time.time() - start_time
    error_msg = (
        f"Failed to produce a working fix after {MAX_ATTEMPTS} attempts. "
        f"Last error: {previous_errors[-1][:500] if previous_errors else 'unknown'}"
    )

    logger.error(f"Repair FAILED for '{finding.title}': {error_msg}")

    result = RepairResult(
        finding_index=finding_index,
        finding_title=finding.title,
        finding_file=finding.file,
        patch=last_patch,
        explanation=last_explanation,
        test_output=previous_errors[-1][:5000] if previous_errors else "",
        tests_passed=False,
        attempts_taken=MAX_ATTEMPTS,
        status=RepairStatus.FAILED,
        confidence=last_confidence,
        duration_seconds=round(duration, 2),
        error=error_msg,
    )

    await emit_event("repair_failed", {
        "finding_index": finding_index,
        "finding_title": finding.title,
        "attempts": MAX_ATTEMPTS,
        "error": error_msg,
        "duration": round(duration, 2),
    })

    return result
