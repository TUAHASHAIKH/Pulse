/**
 * Pulse CLI — `pulse hooks`
 *
 * Manage Git hooks for automatic code reviews.
 *
 *   pulse hooks install    → installs a pre-push hook that triggers Pulse review
 *   pulse hooks uninstall  → removes the pre-push hook
 *   pulse hooks status     → checks if the hook is installed
 *
 * The pre-push hook calls `pulse review --push`, which:
 *   1. Auto-starts the orchestrator + dashboard (if not already running)
 *   2. Opens the dashboard in the browser
 *   3. Runs the review and streams findings to the dashboard
 *   4. Asks the user "Continue pushing? [Y/n]" in the terminal
 */

import { existsSync } from "node:fs";
import { readFile, writeFile, unlink, mkdir, chmod } from "node:fs/promises";
import { join } from "node:path";
import {
  printBanner,
  printSuccess,
  printWarning,
  printError,
  printInfo,
} from "../utils/ui.js";

// ─── Constants ───

const HOOK_MARKER = "# pulse-auto-review";

const HOOK_CONTENT = `#!/bin/sh
${HOOK_MARKER}
# 🫀 Pulse AI — Pre-Push Code Review
# Installed by: pulse hooks install
# Remove with:  pulse hooks uninstall
#
# This hook runs Pulse review before every git push.
# It auto-starts the dashboard, shows findings, and
# asks you to confirm before the push proceeds.

# Connect standard input to the terminal for interactive prompts
exec < /dev/tty || true

pulse review --push
exit $?
`;

// ─── Hooks Command ───

export async function hooksCommand(action: string): Promise<void> {
  const projectRoot = process.cwd();
  const gitDir = join(projectRoot, ".git");
  const hooksDir = join(gitDir, "hooks");
  const hookPath = join(hooksDir, "pre-push");

  // Validate git repo
  if (!existsSync(gitDir)) {
    printError("Not a git repository. Run this command inside a git project.");
    process.exit(1);
  }

  switch (action) {
    case "install":
      await installHook(hooksDir, hookPath);
      break;
    case "uninstall":
      await uninstallHook(hookPath);
      break;
    case "status":
      await hookStatus(hookPath);
      break;
    default:
      printError(`Unknown action: ${action}`);
      printInfo("Usage: pulse hooks <install|uninstall|status>");
      process.exit(1);
  }
}

// ─── Install ───

async function installHook(
  hooksDir: string,
  hookPath: string
): Promise<void> {
  printBanner();

  // Check if hook already exists
  if (existsSync(hookPath)) {
    const existing = await readFile(hookPath, "utf-8");
    if (existing.includes(HOOK_MARKER)) {
      printWarning("Pre-push hook is already installed.");
      printInfo("Run `pulse hooks uninstall` to remove it first.");
      return;
    }

    // There's an existing non-Pulse hook — don't overwrite it
    printWarning(
      "A pre-push hook already exists and was not created by Pulse."
    );
    printInfo(
      "To avoid conflicts, add this line to your existing hook manually:"
    );
    console.log();
    console.log("    pulse review --push || exit $?");
    console.log();
    return;
  }

  // Create hooks directory if it doesn't exist
  await mkdir(hooksDir, { recursive: true });

  // Write the hook file
  await writeFile(hookPath, HOOK_CONTENT, "utf-8");

  // Make it executable (Unix/macOS — no-op on Windows)
  try {
    await chmod(hookPath, 0o755);
  } catch {
    // chmod may fail on Windows — that's fine, git handles it
  }

  console.log();
  printSuccess("Pre-push hook installed!");
  console.log();
  printInfo("Pulse will now automatically review your code before every push.");
  printInfo("The dashboard will open in your browser with live findings.");
  console.log();
  printInfo("To disable: pulse hooks uninstall");
  printInfo("To toggle:  set auto_review_push in .pulse/settings.json");
  console.log();
}

// ─── Uninstall ───

async function uninstallHook(hookPath: string): Promise<void> {
  printBanner();

  if (!existsSync(hookPath)) {
    printInfo("No pre-push hook is installed.");
    return;
  }

  const content = await readFile(hookPath, "utf-8");

  if (!content.includes(HOOK_MARKER)) {
    printWarning("The existing pre-push hook was not created by Pulse.");
    printInfo("Not removing it. Edit .git/hooks/pre-push manually if needed.");
    return;
  }

  await unlink(hookPath);

  console.log();
  printSuccess("Pre-push hook removed.");
  printInfo("Pulse will no longer review code before pushing.");
  console.log();
}

// ─── Status ───

async function hookStatus(hookPath: string): Promise<void> {
  printBanner();

  if (!existsSync(hookPath)) {
    printInfo("Pre-push hook: not installed");
    printInfo("Run `pulse hooks install` to enable automatic reviews.");
    return;
  }

  const content = await readFile(hookPath, "utf-8");

  if (content.includes(HOOK_MARKER)) {
    printSuccess("Pre-push hook: installed ✓");
    printInfo(
      "Pulse will review your code before every push."
    );
  } else {
    printWarning("Pre-push hook: exists (but not managed by Pulse)");
  }
}
