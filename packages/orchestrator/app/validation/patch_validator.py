"""
Validate LLM-generated patches before marking repair as succeeded.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.agents.fix_applicator import _clean_patch
from app.utils.logger import setup_logger

logger = setup_logger("pulse.validation.patch")


@dataclass
class PatchValidation:
    valid: bool
    message: str
    cleaned_patch: str = ""


def _parse_modified_files(patch: str) -> list[str]:
    files: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip().split("\t")[0]
            if path.startswith("b/"):
                path = path[2:]
            files.append(path)
    return files


def validate_patch(
    patch: str,
    project_root: str,
    target_file: str,
) -> PatchValidation:
    """
    Validate a patch using git apply --check against the project root.
    """
    cleaned = _clean_patch(patch)
    if not cleaned.strip():
        return PatchValidation(False, "Empty patch after cleaning")

    modified = _parse_modified_files(cleaned)
    if not modified:
        return PatchValidation(False, "Patch has no file headers")

    normalized_target = target_file.replace("\\", "/").lstrip("/")
    for path in modified:
        norm = path.replace("\\", "/").lstrip("/")
        if norm != normalized_target and not norm.endswith(normalized_target.split("/")[-1]):
            return PatchValidation(
                False,
                f"Patch modifies '{path}' but finding is in '{target_file}'",
            )

    root = Path(project_root)
    if not root.is_dir():
        return PatchValidation(
            False,
            f"Project root not found: {project_root}",
            cleaned_patch=cleaned,
        )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".patch",
        delete=False,
        encoding="utf-8",
        newline="\n",
    ) as tmp:
        tmp.write(cleaned)
        patch_path = tmp.name

    try:
        result = subprocess.run(
            ["git", "apply", "--check", patch_path],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return PatchValidation(True, "Patch applies cleanly", cleaned_patch=cleaned)

        # Fallback to Python patch applier which ignores @@ headers
        from app.agents.fix_applicator import _apply_patch_python_fallback
        success, files_changed, err = _apply_patch_python_fallback(cleaned, str(root), simulate=True)
        if success:
            return PatchValidation(True, "Patch applies cleanly via fallback", cleaned_patch=cleaned)

        stderr = (result.stderr or result.stdout or "git apply --check failed").strip()
        return PatchValidation(False, stderr[:2000], cleaned_patch=cleaned)
    except FileNotFoundError:
        return PatchValidation(
            False,
            "git not found on PATH — cannot verify patch",
            cleaned_patch=cleaned,
        )
    except subprocess.TimeoutExpired:
        return PatchValidation(False, "git apply --check timed out", cleaned_patch=cleaned)
    finally:
        try:
            Path(patch_path).unlink(missing_ok=True)
        except OSError:
            pass
