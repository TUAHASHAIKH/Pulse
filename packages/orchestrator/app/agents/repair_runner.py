"""
Pulse Orchestrator — Repair Runner
"""

from __future__ import annotations

import time
from typing import Optional

from app.agents import repair_agent
from app.sandbox.docker_runner import docker_runner
from app.models.agent_models import Finding, RepairResult, RepairStatus
from app.settings_store import get_setting
from app.validation.patch_validator import validate_patch
from app.ws.socket_server import emit_event
from app.utils.logger import setup_logger

logger = setup_logger("pulse.repair")

DEFAULT_TEST_COMMANDS = {
    "python": "cd /workspace && python -m pytest -x -q 2>&1",
    "node": "cd /workspace && npm test 2>&1",
    "default": "echo 'No test command configured — assuming pass' && exit 0",
}


def _detect_test_command(changed_files: list[str]) -> str:
    extensions = {f.rsplit(".", 1)[-1].lower() for f in changed_files if "." in f}
    if extensions & {"py"}:
        return DEFAULT_TEST_COMMANDS["python"]
    if extensions & {"js", "ts", "jsx", "tsx"}:
        return DEFAULT_TEST_COMMANDS["node"]
    return DEFAULT_TEST_COMMANDS["default"]


def _validate_patch_or_error(
    patch: str,
    project_path: Optional[str],
    finding: Finding,
) -> tuple[bool, str, str]:
    """Returns (ok, error_message, cleaned_patch)."""
    if not project_path:
        return True, "", patch

    validation = validate_patch(patch, project_path, finding.file)
    if validation.valid:
        return True, "", validation.cleaned_patch or patch

    return False, validation.message, validation.cleaned_patch or patch


async def run_repair(
    finding: Finding,
    finding_index: int,
    diff: str,
    changed_files: list[str],
    project_path: Optional[str] = None,
    test_command: Optional[str] = None,
) -> RepairResult:
    start_time = time.time()
    max_attempts = int(get_setting("repair_max_attempts", 3))

    if not test_command:
        test_command = _detect_test_command(changed_files)

    logger.info(
        f"Starting repair for finding '{finding.title}' "
        f"in {finding.file}:{finding.line}"
    )

    await emit_event("repair_started", {
        "finding_index": finding_index,
        "finding_title": finding.title,
        "finding_file": finding.file,
        "max_attempts": max_attempts,
    })

    previous_errors: list[str] = []
    last_patch = ""
    last_explanation = ""
    last_confidence = 0.0

    docker_available = await docker_runner.is_available()

    for attempt in range(1, max_attempts + 1):
        logger.info(f"Repair attempt {attempt}/{max_attempts}...")

        await emit_event("repair_attempt", {
            "finding_index": finding_index,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "status": "generating_fix",
        })

        fix_result = await repair_agent.generate_fix(
            finding=finding,
            diff=diff,
            previous_errors=previous_errors if previous_errors else None,
            project_root=project_path,
        )

        last_patch = fix_result["patch"]
        last_explanation = fix_result["explanation"]
        last_confidence = fix_result["confidence"]

        if not last_patch or last_confidence == 0.0:
            logger.warning(
                f"Repair Agent returned empty/zero-confidence patch on attempt {attempt}"
            )
            previous_errors.append(
                f"Repair Agent returned no viable patch: {last_explanation}"
            )
            continue

        ok, patch_error, cleaned = _validate_patch_or_error(
            last_patch, project_path, finding
        )
        if not ok:
            logger.warning(f"Patch validation failed on attempt {attempt}: {patch_error}")
            previous_errors.append(f"Patch validation failed: {patch_error}")
            continue

        last_patch = cleaned

        await emit_event("repair_attempt", {
            "finding_index": finding_index,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "status": "testing_fix",
            "patch_length": len(last_patch),
            "confidence": last_confidence,
        })

        if docker_available:
            container_id = None
            try:
                container_id = await docker_runner.create_sandbox(project_path)
                patch_applied = await docker_runner.apply_patch(container_id, last_patch)
                if not patch_applied:
                    previous_errors.append(
                        "Failed to apply patch in sandbox (git apply failed)"
                    )
                    continue

                test_result = await docker_runner.run_tests(container_id, test_command)

                if test_result.passed:
                    duration = time.time() - start_time
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
                        "status": RepairStatus.SUCCEEDED.value,
                    })
                    return result

                error_output = test_result.stdout or test_result.stderr
                previous_errors.append(error_output[:3000])
                logger.warning(
                    f"Repair attempt {attempt} failed — tests exited with "
                    f"code {test_result.exit_code}"
                )

            except Exception as e:
                logger.error(f"Sandbox error on attempt {attempt}: {e}")
                previous_errors.append(f"Sandbox error: {str(e)}")
            finally:
                if container_id:
                    try:
                        await docker_runner.cleanup(container_id)
                    except Exception:
                        pass
        else:
            duration = time.time() - start_time
            logger.warning(
                "Docker not available — patch passed git apply --check, "
                "marking as UNVERIFIED"
            )
            result = RepairResult(
                finding_index=finding_index,
                finding_title=finding.title,
                finding_file=finding.file,
                patch=last_patch,
                explanation=last_explanation,
                test_output="Docker not available — patch validated with git apply --check only",
                tests_passed=False,
                attempts_taken=attempt,
                status=RepairStatus.UNVERIFIED,
                confidence=last_confidence,
                duration_seconds=round(duration, 2),
            )
            await emit_event("repair_succeeded", {
                "finding_index": finding_index,
                "finding_title": finding.title,
                "attempt": attempt,
                "patch": last_patch,
                "explanation": last_explanation,
                "test_output": result.test_output,
                "confidence": last_confidence,
                "duration": round(duration, 2),
                "docker_verified": False,
                "status": RepairStatus.UNVERIFIED.value,
            })
            return result

    duration = time.time() - start_time
    error_msg = (
        f"Failed to produce a working fix after {max_attempts} attempts. "
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
        attempts_taken=max_attempts,
        status=RepairStatus.FAILED,
        confidence=last_confidence,
        duration_seconds=round(duration, 2),
        error=error_msg,
    )

    await emit_event("repair_failed", {
        "finding_index": finding_index,
        "finding_title": finding.title,
        "attempts": max_attempts,
        "error": error_msg,
        "duration": round(duration, 2),
    })

    return result
