"""
Pulse Orchestrator — Fix Applicator

Handles the three methods of delivering a verified fix to the user:
  1. Apply Locally  — uses `git apply` on the user's local filesystem
  2. PR Comment     — posts the patch as a GitHub PR comment
  3. Commit to Branch — pushes the fix to a pulse/fix-{id} branch on GitHub

Each method is independent and safe:
  - "Apply locally" modifies files but does NOT commit
  - "PR comment" only adds a comment, no code changes
  - "Commit to branch" creates a NEW branch, never touches the user's branch
"""

import subprocess
import base64
from pathlib import Path
from typing import Optional

from app.models.agent_models import FixApplicationResponse
from app.integrations.github_client import github_client
from app.utils.logger import setup_logger

logger = setup_logger("pulse.fix")


def _clean_patch(patch: str) -> str:
    """
    Clean and normalize an LLM-generated patch so `git apply` can read it reliably.
    - Strips markdown code block formatting if present (```diff ... ```)
    - Normalizes line endings to LF (\n)
    - Ensures blank context lines inside diff hunks start with a space (' ')
    - Ensures every patch ends with a newline (\n)
    """
    if not patch:
        return ""

    lines = patch.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned = []
    in_diff = False
    in_hunk = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped_left = line.lstrip()
        if stripped_left.startswith("```") or stripped_left == "`":
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            in_diff = True
            in_hunk = False
            cleaned.append(line)
            continue
        if line.startswith("@@ "):
            in_hunk = True
            cleaned.append(line)
            continue
        if in_hunk:
            if line == "":
                cleaned.append(" ")
            elif line[0] not in (" ", "+", "-", "\\"):
                cleaned.append(" " + line)
            else:
                cleaned.append(line)
        elif in_diff:
            cleaned.append(line)
        else:
            if line.startswith("diff --git"):
                cleaned.append(line)

    result = "\n".join(cleaned).strip()
    if result:
        result += "\n"
    return result


def _parse_patch_hunks(patch: str) -> dict[str, list[tuple[list[str], list[str], list[str], list[str]]]]:
    """
    Parse a unified diff into per-file hunks.

    Returns:
        {relative_path: [(old_lines, new_lines, removals, additions), ...]}
    """
    lines = patch.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    current_file = None
    file_hunks: dict[str, list[tuple[list[str], list[str], list[str], list[str]]]] = {}

    old_lines: list[str] = []
    new_lines: list[str] = []
    just_removals: list[str] = []
    just_additions: list[str] = []
    in_hunk = False

    def _flush_hunk() -> None:
        nonlocal old_lines, new_lines, just_removals, just_additions, in_hunk
        if current_file and in_hunk and (old_lines or new_lines):
            file_hunks.setdefault(current_file, []).append(
                (list(old_lines), list(new_lines), list(just_removals), list(just_additions))
            )
        old_lines = []
        new_lines = []
        just_removals = []
        just_additions = []
        in_hunk = False

    for line in lines:
        if line.startswith("+++ "):
            _flush_hunk()
            path_str = line[4:].strip().split("\t")[0]
            if path_str.startswith("b/"):
                path_str = path_str[2:]
            elif path_str.startswith("a/"):
                path_str = path_str[2:]
            current_file = path_str
            file_hunks.setdefault(current_file, [])
            continue

        if line.startswith("@@ "):
            _flush_hunk()
            in_hunk = True
            continue

        if in_hunk and current_file:
            if line.startswith("-"):
                val = line[1:]
                old_lines.append(val)
                just_removals.append(val)
            elif line.startswith("+"):
                val = line[1:]
                new_lines.append(val)
                just_additions.append(val)
            elif line.startswith(" ") or line == "":
                val = line[1:] if line.startswith(" ") else ""
                old_lines.append(val)
                new_lines.append(val)

    _flush_hunk()
    return file_hunks


def _apply_hunks_to_content(
    content: str,
    hunks: list[tuple[list[str], list[str], list[str], list[str]]],
) -> tuple[bool, str, str]:
    """Apply parsed hunks to in-memory file content. Returns (ok, new_content, error)."""
    for old_lines_list, new_lines_list, removals_list, additions_list in hunks:
        old_text = "\n".join(old_lines_list)
        new_text = "\n".join(new_lines_list)

        if old_text in content:
            content = content.replace(old_text, new_text, 1)
            continue

        if removals_list:
            removals_text = "\n".join(removals_list)
            additions_text = "\n".join(additions_list)
            if removals_text in content and content.count(removals_text) == 1:
                content = content.replace(removals_text, additions_text, 1)
            else:
                return False, content, "Could not locate unique matching code block"
        elif additions_list and not removals_list:
            return False, content, "Context mismatch for additions-only hunk"

    return True, content, ""


def _apply_patch_python_fallback(patch: str, project_root: str, simulate: bool = False) -> tuple[bool, list[str], str]:
    """
    Fallback patch applier implemented in Python.
    If git apply fails (due to hunk offset mismatch, trailing whitespace, or formatting),
    this parses the target file(s) and applies the removals/additions
    by finding the matching blocks in the file.
    """
    file_hunks = _parse_patch_hunks(patch)
    if not file_hunks:
        return False, [], "Could not parse filenames from patch"

    files_changed = []
    root_path = Path(project_root)

    for rel_file, hunks in file_hunks.items():
        abs_path = root_path / rel_file
        if not abs_path.exists():
            matches = list(root_path.rglob(Path(rel_file).name))
            matches = [m for m in matches if ".git" not in m.parts and "node_modules" not in m.parts]
            if matches:
                abs_path = matches[0]
            else:
                return False, files_changed, f"Target file not found: {rel_file}"

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return False, files_changed, f"Could not read {abs_path}: {e}"

        original_content = content
        ok, content, err = _apply_hunks_to_content(content, hunks)
        if not ok:
            return False, files_changed, f"{err} in {abs_path.name}"

        if content != original_content:
            if not simulate:
                try:
                    abs_path.write_text(content, encoding="utf-8")
                    files_changed.append(rel_file)
                except Exception as e:
                    return False, files_changed, f"Could not write {abs_path}: {e}"
            else:
                files_changed.append(rel_file)

    if not files_changed:
        return False, [], "No changes applied (content already up to date or patch empty)"

    return True, files_changed, ""


async def apply_locally(
    patch: str,
    project_root: str,
) -> FixApplicationResponse:
    """
    Apply a patch to the user's local filesystem.
    First cleans the patch and attempts `git apply` with whitespace tolerance flags.
    If git apply fails, falls back to a resilient Python patch applier that directly modifies the file.
    """
    import tempfile
    import os

    logger.info(f"Applying fix locally to {project_root}...")

    if not os.path.isdir(project_root):
        return FixApplicationResponse(
            success=False,
            method="local",
            message=f"Project directory not found: {project_root}",
        )

    # Step 1: Clean and normalize patch
    cleaned_patch = _clean_patch(patch)

    # Step 2: Try git apply with whitespace-forgiving flags
    for flags in (
        ["--whitespace=fix", "--ignore-space-change", "--ignore-whitespace"],
        ["--whitespace=nowarn", "--ignore-space-change", "--ignore-whitespace", "--recount", "-C1"],
        ["--whitespace=nowarn", "--ignore-space-change", "--ignore-whitespace", "--recount", "-C0", "--unidiff-zero"],
    ):
        patch_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, encoding="utf-8"
            ) as f:
                f.write(cleaned_patch)
                patch_file = f.name

            stat_res = subprocess.run(
                ["git", "apply", "--stat"] + flags + [patch_file],
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            apply_res = subprocess.run(
                ["git", "apply"] + flags + [patch_file],
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if patch_file and os.path.exists(patch_file):
                os.unlink(patch_file)

            if apply_res.returncode == 0:
                files_changed = []
                for line in stat_res.stdout.strip().split("\n"):
                    if "|" in line:
                        filename = line.split("|")[0].strip()
                        if filename:
                            files_changed.append(filename)
                logger.info(f"Fix applied locally via git apply ({len(files_changed)} file(s) changed)")
                return FixApplicationResponse(
                    success=True,
                    method="local",
                    message=f"Fix applied to {len(files_changed)} file(s). "
                            f"Changes are unstaged — commit when ready.",
                    files_changed=files_changed,
                )
        except Exception:
            if patch_file and os.path.exists(patch_file):
                os.unlink(patch_file)
            continue

    # Step 3: If all git apply attempts fail, use Python fallback applier
    logger.info("git apply flags failed; attempting Python fallback patch applier...")
    success, files_changed, error_msg = _apply_patch_python_fallback(cleaned_patch, project_root)
    if success:
        logger.info(f"Fix applied locally via Python fallback ({len(files_changed)} file(s) changed)")
        return FixApplicationResponse(
            success=True,
            method="local",
            message=f"Fix applied to {len(files_changed)} file(s). "
                    f"Changes are unstaged — commit when ready.",
            files_changed=files_changed,
        )

    logger.error(f"Failed to apply patch: {error_msg}")
    return FixApplicationResponse(
        success=False,
        method="local",
        message=f"Could not apply patch: {error_msg}",
    )


async def post_as_pr_comment(
    patch: str,
    explanation: str,
    finding_title: str,
    repo: str,
    pr_number: int,
) -> FixApplicationResponse:
    """
    Post the fix as a formatted comment on a GitHub PR.

    Args:
        patch: Unified diff patch text
        explanation: What the fix does
        finding_title: Title of the finding being fixed
        repo: GitHub repo full name (e.g. 'tuaha/acme-shop')
        pr_number: PR number to comment on

    Returns:
        FixApplicationResponse with the comment URL
    """
    logger.info(f"Posting fix as PR comment on {repo}#{pr_number}...")

    # Format the comment
    comment_body = (
        f"## 🔧 Pulse Repair Agent — Suggested Fix\n\n"
        f"**Finding:** {finding_title}\n\n"
        f"**Explanation:** {explanation}\n\n"
        f"<details>\n"
        f"<summary>📋 View Patch</summary>\n\n"
        f"```diff\n{patch}\n```\n\n"
        f"</details>\n\n"
        f"---\n"
        f"*To apply this fix locally, run:*\n"
        f"```bash\n"
        f"# Save the patch from above to a file, then:\n"
        f"git apply fix.patch\n"
        f"```\n"
    )

    try:
        result = await github_client.post_pr_comment(repo, pr_number, comment_body)
        comment_url = result.get("html_url", "")

        logger.info(f"Fix posted as comment: {comment_url}")
        return FixApplicationResponse(
            success=True,
            method="pr_comment",
            message=f"Fix posted as PR comment on {repo}#{pr_number}",
            comment_url=comment_url,
        )

    except Exception as e:
        logger.error(f"Failed to post PR comment: {e}")
        return FixApplicationResponse(
            success=False,
            method="pr_comment",
            message=f"Failed to post PR comment: {str(e)}",
        )


async def commit_to_branch(
    patch: str,
    explanation: str,
    finding_title: str,
    review_id: str,
    repo: str,
    pr_number: int,
) -> FixApplicationResponse:
    """
    Commit the fix to a new branch on GitHub.

    Creates a branch named 'pulse/fix-{review_id}' from the PR's head,
    applies the patch via Git Data API (blob → tree → commit → ref).
    """
    logger.info(f"Committing fix to new branch for {repo}#{pr_number}...")

    branch_name = f"pulse/fix-{review_id}"
    cleaned_patch = _clean_patch(patch)
    file_hunks = _parse_patch_hunks(cleaned_patch)

    if not file_hunks:
        return FixApplicationResponse(
            success=False,
            method="branch",
            message="Could not parse patch — no file changes found.",
        )

    try:
        client = github_client._get_client()

        pr_response = await client.get(f"/repos/{repo}/pulls/{pr_number}")
        pr_response.raise_for_status()
        head_sha = pr_response.json()["head"]["sha"]

        commit_response = await client.get(f"/repos/{repo}/git/commits/{head_sha}")
        commit_response.raise_for_status()
        base_tree_sha = commit_response.json()["tree"]["sha"]

        ref_response = await client.post(
            f"/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": head_sha},
        )
        if ref_response.status_code == 422:
            ref_response = await client.patch(
                f"/repos/{repo}/git/refs/heads/{branch_name}",
                json={"sha": head_sha, "force": True},
            )
        ref_response.raise_for_status()

        tree_entries = []
        for rel_path, hunks in file_hunks.items():
            content_resp = await client.get(
                f"/repos/{repo}/contents/{rel_path}",
                params={"ref": head_sha},
            )
            if content_resp.status_code == 404:
                current_content = ""
            else:
                content_resp.raise_for_status()
                encoded = content_resp.json().get("content", "")
                current_content = base64.b64decode(encoded).decode("utf-8", errors="replace")

            ok, new_content, err = _apply_hunks_to_content(current_content, hunks)
            if not ok:
                return FixApplicationResponse(
                    success=False,
                    method="branch",
                    message=f"Failed to apply patch to {rel_path}: {err}",
                )

            blob_response = await client.post(
                f"/repos/{repo}/git/blobs",
                json={"content": new_content, "encoding": "utf-8"},
            )
            blob_response.raise_for_status()
            blob_sha = blob_response.json()["sha"]
            tree_entries.append({
                "path": rel_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            })

        tree_response = await client.post(
            f"/repos/{repo}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        tree_response.raise_for_status()
        new_tree_sha = tree_response.json()["sha"]

        commit_message = f"fix: [pulse] {finding_title}\n\n{explanation}"
        new_commit_response = await client.post(
            f"/repos/{repo}/git/commits",
            json={
                "message": commit_message,
                "tree": new_tree_sha,
                "parents": [head_sha],
            },
        )
        new_commit_response.raise_for_status()
        new_commit_sha = new_commit_response.json()["sha"]

        await client.patch(
            f"/repos/{repo}/git/refs/heads/{branch_name}",
            json={"sha": new_commit_sha},
        )

        logger.info(f"Fix committed to branch {branch_name} ({new_commit_sha[:7]})")
        return FixApplicationResponse(
            success=True,
            method="branch",
            message=(
                f"Fix committed to branch '{branch_name}' "
                f"({len(tree_entries)} file(s) changed)."
            ),
            branch_name=branch_name,
            files_changed=list(file_hunks.keys()),
        )

    except Exception as e:
        logger.error(f"Failed to commit to branch: {e}")
        return FixApplicationResponse(
            success=False,
            method="branch",
            message=f"Failed to commit to branch: {str(e)}",
        )


async def auto_deliver_repairs(
    repair_results: list,
    review_id: str,
    project_root: str,
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
) -> list[FixApplicationResponse]:
    """
    Auto-deliver verified repairs based on fix_delivery setting.

    Skips when fix_delivery is 'ask' (manual dashboard flow).
    """
    from app.models.agent_models import RepairStatus
    from app.settings_store import get_setting

    delivery_mode = get_setting("fix_delivery", "ask")
    if delivery_mode == "ask":
        return []

    delivered: list[FixApplicationResponse] = []

    for repair in repair_results:
        eligible_statuses = {RepairStatus.SUCCEEDED}
        if delivery_mode == "local":
            eligible_statuses.add(RepairStatus.UNVERIFIED)

        if repair.status not in eligible_statuses or not repair.patch:
            continue

        result: Optional[FixApplicationResponse] = None

        if delivery_mode == "local":
            if not project_root:
                logger.warning("fix_delivery=local but no project_root — skipping")
                continue
            result = await apply_locally(repair.patch, project_root)
        elif delivery_mode == "pr_comment":
            if not repo or not pr_number:
                logger.warning("fix_delivery=pr_comment but no repo/pr_number — skipping")
                continue
            result = await post_as_pr_comment(
                patch=repair.patch,
                explanation=repair.explanation,
                finding_title=repair.finding_title,
                repo=repo,
                pr_number=pr_number,
            )
        elif delivery_mode == "branch":
            if not repo or not pr_number:
                logger.warning("fix_delivery=branch but no repo/pr_number — skipping")
                continue
            result = await commit_to_branch(
                patch=repair.patch,
                explanation=repair.explanation,
                finding_title=repair.finding_title,
                review_id=review_id,
                repo=repo,
                pr_number=pr_number,
            )

        if result:
            delivered.append(result)
            logger.info(
                f"Auto-delivered fix for '{repair.finding_title}' "
                f"via {delivery_mode}: success={result.success}"
            )

    return delivered
