/**
 * Pulse CLI — `pulse review`
 *
 * Trigger a code review from the terminal.
 *   - `pulse review`              → sends `git diff HEAD` to the orchestrator
 *   - `pulse review --pr org/repo#42` → sends the PR reference
 *   - `pulse review --all`        → full repository audit (scans all files)
 *   - `pulse review --all --force` → re-scan everything ignoring cache
 *   - `pulse review --push`       → pre-push gate: auto-start, dashboard, review, confirm
 */

import { exec } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import * as readline from "node:readline";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import chalk from "chalk";
import {
  printBanner,
  printCompactBanner,
  printSuccess,
  printError,
  printInfo,
  printWarning,
  createSpinner,
  printReviewSummary,
  printGuidanceBox,
  printShutdown,
  PULSE_CYAN,
  PULSE_DIM,
  PULSE_AMBER,
  PULSE_GREEN,
  PULSE_RED,
  PULSE_GRAY,
} from "../utils/ui.js";
import { ensureVenv, installDeps } from "../utils/python.js";
import {
  spawnOrchestrator,
  spawnDashboard,
  writePidFile,
  waitForHealthy,
  type SpawnOptions,
} from "../utils/process.js";
import type { ChildProcess } from "node:child_process";

const execAsync = promisify(exec);

// ─── Review Command ───

export async function reviewCommand(options: {
  pr?: string;
  port?: number;
  all?: boolean;
  force?: boolean;
  push?: boolean;
}): Promise<void> {
  const orchestratorPort = options.port || 8000;
  const dashboardPort = 3000;
  const baseUrl = `http://localhost:${orchestratorPort}`;

  // ── Pre-Push Mode ──
  if (options.push) {
    await handlePushReview(orchestratorPort, dashboardPort, baseUrl);
    return;
  }

  printBanner();

  // 1. Check that the orchestrator is running
  const healthSpinner = createSpinner("Connecting to orchestrator...");
  healthSpinner.start();

  try {
    const healthRes = await fetch(`${baseUrl}/health`);
    if (!healthRes.ok) throw new Error("unhealthy");
    healthSpinner.succeed("Connected to orchestrator");
  } catch {
    healthSpinner.fail(
      `Could not connect to orchestrator at ${baseUrl}\n` +
      '           Run "pulse start" first.'
    );
    process.exit(1);
  }

  // ── Full Audit Mode ──
  if (options.all) {
    const auditSpinner = createSpinner(
      options.force
        ? "Running full repository audit (force re-scan)..."
        : "Running full repository audit..."
    );
    auditSpinner.start();

    try {
      const res = await fetch(`${baseUrl}/api/review/full`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: options.force || false }),
      });

      const data = await res.json() as {
        status: string;
        review_id?: string;
        message?: string;
        scan_stats?: {
          files_total: number;
          files_to_scan: number;
          files_skipped: number;
          files_oversized: number;
        };
        results?: Array<{
          agent_name: string;
          findings: Array<{
            severity: string;
            title: string;
            file: string;
            description: string;
          }>;
        }>;
      };

      if (data.status === "error") {
        auditSpinner.fail(`Audit failed: ${data.message}`);
        process.exit(1);
      }

      const stats = data.scan_stats;
      if (stats) {
        auditSpinner.succeed(
          `Audit complete — scanned ${stats.files_to_scan} files, ` +
          `${stats.files_skipped} unchanged (skipped), ` +
          `${stats.files_oversized} oversized (skipped)`
        );
      } else {
        auditSpinner.succeed(`Audit complete (ID: ${data.review_id})`);
      }

      // Display results
      const results = data.results || [];

      if (results.length === 0) {
        printSuccess("No findings — your codebase looks good! 🎉");
        return;
      }

      // Use styled review summary
      const auditFindings = results.map(r => ({
        label: r.agent_name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
        count: r.findings.length,
        icon: r.findings.length === 0 ? "✅" : "🟡",
      }));
      let auditTotal = 0;
      let auditSev = { critical: 0, warning: 0, info: 0 };
      for (const r of results) {
        for (const f of r.findings) {
          auditTotal++;
          if (f.severity === "critical") auditSev.critical++;
          else if (f.severity === "warning") auditSev.warning++;
          else auditSev.info++;
        }
      }
      printReviewSummary(auditFindings, 0, auditTotal, auditSev);

      // Detailed findings
      for (const agentResult of results) {
        if (agentResult.findings.length === 0) continue;

        console.log();
        console.log("  " + PULSE_CYAN("▸") + " " + chalk.bold.white(agentResult.agent_name));

        for (const finding of agentResult.findings) {
          const severityColor =
            finding.severity === "critical" ? PULSE_RED
              : finding.severity === "warning" ? PULSE_AMBER
              : chalk.blue;

          const badge = severityColor(` ${finding.severity.toUpperCase()} `);
          console.log(`    ${badge} ${chalk.white(finding.title)}`);
          console.log(`         ${PULSE_DIM(finding.file)}`);
          console.log(`         ${PULSE_GRAY(finding.description)}`);
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      auditSpinner.fail(`Audit request failed: ${message}`);
      process.exit(1);
    }

    return;
  }

  // ── Diff / PR Mode (existing behavior) ──

  // 2. Build the review payload
  const projectRoot = process.cwd();
  let body: Record<string, string | number>;

  if (options.pr) {
    // Parse "owner/repo#123" format
    const match = options.pr.match(/^(.+?)#(\d+)$/);
    if (!match) {
      printError(
        'Invalid PR format. Use: pulse review --pr owner/repo#123'
      );
      process.exit(1);
    }

    const [, repo, prNumber] = match;
    body = { repo, pr_number: parseInt(prNumber, 10), project_root: projectRoot };
    printInfo(`Reviewing PR #${prNumber} on ${repo}`);
  } else {
    // Get diff from git
    const diffSpinner = createSpinner("Getting diff from git...");
    diffSpinner.start();

    try {
      // Try staged changes first, fall back to all changes
      let { stdout: diff } = await execAsync("git diff --cached", {
        maxBuffer: 1024 * 1024 * 5,
      });

      if (!diff.trim()) {
        const result = await execAsync("git diff HEAD", {
          maxBuffer: 1024 * 1024 * 5,
        });
        diff = result.stdout;
      }

      if (!diff.trim()) {
        diffSpinner.fail("No changes detected (git diff is empty)");
        printInfo("Stage changes with `git add` or make modifications first.");
        printInfo("Tip: Use `pulse review --all` to scan the entire repository.");
        process.exit(1);
      }

      body = { diff, project_root: projectRoot };
      const lineCount = diff.split("\n").length;
      diffSpinner.succeed(`Got diff (${lineCount} lines)`);
    } catch {
      diffSpinner.fail(
        "Failed to get git diff. Are you in a git repository?"
      );
      process.exit(1);
    }
  }

  // 3. Send to orchestrator
  const reviewSpinner = createSpinner("Running review...");
  reviewSpinner.start();

  try {
    const res = await fetch(`${baseUrl}/api/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json() as {
      status: string;
      review_id?: string;
      message?: string;
      results?: Array<{
        agent_name: string;
        findings: Array<{
          severity: string;
          title: string;
          file: string;
          description: string;
        }>;
      }>;
    };

    if (data.status === "error") {
      reviewSpinner.fail(`Review failed: ${data.message}`);
      process.exit(1);
    }

    reviewSpinner.succeed(`Review complete (ID: ${data.review_id})`);

    // 4. Display results
    const results = data.results || [];

    if (results.length === 0) {
      printSuccess("No findings — your code looks good! 🎉");
      return;
    }

    // Use styled review summary
    const diffFindings = results.map(r => ({
      label: r.agent_name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
      count: r.findings.length,
      icon: r.findings.length === 0 ? "✅" : "🟡",
    }));
    let diffTotal = 0;
    let diffSev = { critical: 0, warning: 0, info: 0 };
    for (const r of results) {
      for (const f of r.findings) {
        diffTotal++;
        if (f.severity === "critical") diffSev.critical++;
        else if (f.severity === "warning") diffSev.warning++;
        else diffSev.info++;
      }
    }
    printReviewSummary(diffFindings, 0, diffTotal, diffSev);

    // Detailed findings
    for (const agentResult of results) {
      if (agentResult.findings.length === 0) continue;

      console.log();
      console.log("  " + PULSE_CYAN("▸") + " " + chalk.bold.white(agentResult.agent_name));

      for (const finding of agentResult.findings) {
        const severityColor =
          finding.severity === "critical" ? PULSE_RED
            : finding.severity === "warning" ? PULSE_AMBER
            : chalk.blue;

        const badge = severityColor(` ${finding.severity.toUpperCase()} `);
        console.log(`    ${badge} ${chalk.white(finding.title)}`);
        console.log(`         ${PULSE_DIM(finding.file)}`);
        console.log(`         ${PULSE_GRAY(finding.description)}`);
      }
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    reviewSpinner.fail(`Review request failed: ${message}`);
    process.exit(1);
  }
}


// ─── Pre-Push Review Mode ───

/**
 * Handles the `pulse review --push` flow:
 *   1. Read settings — exit 0 if auto_review_push is disabled
 *   2. Auto-start orchestrator + dashboard if not already running
 *   3. Open dashboard in browser
 *   4. Get the diff being pushed
 *   5. Send to orchestrator for review
 *   6. Print summary in terminal
 *   7. Ask "Continue pushing? [Y/n]" (if block_push is enabled)
 */
async function handlePushReview(
  orchestratorPort: number,
  dashboardPort: number,
  baseUrl: string
): Promise<void> {
  const projectRoot = process.cwd();

  // ── Step 1: Read settings ──
  const settings = await readPulseSettings(projectRoot);

  if (!settings.auto_review_push) {
    // Silently exit — zero overhead, push proceeds
    process.exit(0);
  }

  printCompactBanner("Pre-Push Review");

  // ── Step 2: Check if orchestrator is already running ──
  let weSpawnedIt = false;
  const isRunning = await isOrchestratorRunning(baseUrl);

  if (isRunning) {
    printInfo("Orchestrator already running — reusing it");
  } else {
    // Auto-start orchestrator + dashboard
    const startSpinner = createSpinner("Starting Pulse...");
    startSpinner.start();

    try {
      await autoStartPulse(projectRoot, orchestratorPort, dashboardPort);
      weSpawnedIt = true;
      startSpinner.succeed("Pulse started (orchestrator + dashboard)");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      startSpinner.fail(`Failed to start Pulse: ${message}`);
      // Don't block the push if Pulse can't start
      printWarning("Push will proceed without review.");
      process.exit(0);
    }
  }

  // ── Step 3: Open dashboard in browser ──
  try {
    await openBrowser(`http://localhost:${dashboardPort}`);
    printInfo("Dashboard opened in browser");
  } catch {
    printInfo(`Dashboard available at http://localhost:${dashboardPort}`);
  }

  // ── Step 3.5: Wait for dashboard WebSocket to connect ──
  // This ensures the dashboard is ready to receive the real-time events
  // so the user sees the animations and all findings from the start.
  const waitSpinner = createSpinner("Waiting for dashboard to connect...");
  waitSpinner.start();
  await new Promise(r => setTimeout(r, 4000));
  waitSpinner.succeed("Dashboard ready");

  // ── Step 4: Get the diff being pushed ──
  const diffSpinner = createSpinner("Getting diff...");
  diffSpinner.start();

  let diff: string;
  try {
    diff = await getPushDiff();
    if (!diff.trim()) {
      diffSpinner.succeed("No changes to review");
      process.exit(0);
    }
    const lineCount = diff.split("\n").length;
    diffSpinner.succeed(`Got diff (${lineCount} lines)`);
  } catch {
    diffSpinner.fail("Failed to get git diff");
    printWarning("Push will proceed without review.");
    process.exit(0);
  }

  // ── Step 5: Send to orchestrator ──
  const reviewSpinner = createSpinner("Running review...");
  reviewSpinner.start();

  let totalFindings = 0;
  let criticalCount = 0;
  let warningCount = 0;
  let infoCount = 0;

  try {
    const res = await fetch(`${baseUrl}/api/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ diff, project_root: projectRoot }),
    });

    const data = await res.json() as {
      status: string;
      review_id?: string;
      message?: string;
      results?: Array<{
        agent_name: string;
        findings: Array<{
          severity: string;
          title: string;
          file: string;
        }>;
      }>;
      repair_results?: Array<{
        status: string;
        finding_title: string;
      }>;
    };

    if (data.status === "error") {
      reviewSpinner.fail(`Review failed: ${data.message}`);
      printWarning("Push will proceed without review.");
      process.exit(0);
    }

    const results = data.results || [];
    const repairs = data.repair_results || [];
    const successfulRepairs = repairs.filter(r => r.status === "succeeded").length;

    // Count findings by severity
    for (const agentResult of results) {
      for (const finding of agentResult.findings) {
        totalFindings++;
        if (finding.severity === "critical") criticalCount++;
        else if (finding.severity === "warning") warningCount++;
        else infoCount++;
      }
    }

    reviewSpinner.succeed(`Review complete`);

    // ── Step 6: Print summary using styled box ──
    const pushFindings = results.map(r => ({
      label: r.agent_name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
      count: r.findings.length,
      icon: r.findings.length === 0 ? "✅" : "🟡",
    }));

    printReviewSummary(
      pushFindings,
      successfulRepairs,
      totalFindings,
      { critical: criticalCount, warning: warningCount, info: infoCount }
    );

  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    reviewSpinner.fail(`Review failed: ${message}`);
    printWarning("Push will proceed without review.");
    process.exit(0);
  }

  // ── Step 7: Ask to continue (if block_push is enabled) ──
  let shouldPush = true;
  if (settings.block_push) {
    if (totalFindings === 0) {
      shouldPush = await askQuestion("Continue pushing?", true);
    } else {
      printGuidanceBox([
        `Type ${chalk.bold("'n'")} below to cancel this push`,
        `Open the ${chalk.bold("Dashboard")} and click ${PULSE_CYAN("Apply Locally")} on desired fixes`,
        `Run ${chalk.bold.white("git add . && git commit -m 'pulse fixes'")}`,
        `Run ${chalk.bold.white("git push")} again — Pulse will confirm it's clean`,
      ]);
      
      shouldPush = await askQuestion("Bypass and push without fixes?", false);
    }

    if (!shouldPush) {
      console.log();
      console.log("  " + PULSE_RED("✖") + "  " + chalk.bold.white("Push blocked") + PULSE_DIM(" — apply fixes and try again"));
      
      // Wait for user to close dashboard if we spawned it
      if (weSpawnedIt) {
        console.log();
        printInfo("Dashboard is still running — apply fixes there");
        const closeIt = await askQuestion("Close the dashboard now?", true);
        if (closeIt) {
          try {
            const { killProcessTree, readPidFile } = await import("../utils/process.js");
            const pids = await readPidFile(projectRoot);
            if (pids?.orchestratorPid) await killProcessTree(pids.orchestratorPid);
            if (pids?.dashboardPid) await killProcessTree(pids.dashboardPid);
          } catch {}
        }
      }
      process.exit(1); // exit 1 = block the push
    }
  }

  // If user says YES to push
  if (weSpawnedIt) {
    console.log();
    const closeIt = await askQuestion("Close the dashboard before push completes?", true);
    if (closeIt) {
      try {
        const { killProcessTree, readPidFile } = await import("../utils/process.js");
        const pids = await readPidFile(projectRoot);
        if (pids?.orchestratorPid) await killProcessTree(pids.orchestratorPid);
        if (pids?.dashboardPid) await killProcessTree(pids.dashboardPid);
      } catch {}
    } else {
      printInfo("Dashboard running in background — run pulse stop when done");
    }
  }

  // Push proceeds
  process.exit(0);
}


// ─── Helpers ───

/**
 * Read .pulse/settings.json from the project root.
 * Returns defaults if file doesn't exist.
 */
async function readPulseSettings(projectRoot: string): Promise<{
  auto_review_push: boolean;
  block_push: boolean;
}> {
  const defaults = {
    auto_review_push: false,
    block_push: true,
  };

  const settingsPath = join(projectRoot, ".pulse", "settings.json");
  if (!existsSync(settingsPath)) {
    return defaults;
  }

  try {
    const content = await readFile(settingsPath, "utf-8");
    const parsed = JSON.parse(content);
    return {
      auto_review_push: parsed.auto_review_push ?? defaults.auto_review_push,
      block_push: parsed.block_push ?? defaults.block_push,
    };
  } catch {
    return defaults;
  }
}

/**
 * Check if the orchestrator is already running.
 */
async function isOrchestratorRunning(baseUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Get the diff of commits being pushed (compared to the remote).
 */
async function getPushDiff(): Promise<string> {
  // Get the current branch name
  const { stdout: branch } = await execAsync("git rev-parse --abbrev-ref HEAD", {
    maxBuffer: 1024 * 1024,
  });
  const currentBranch = branch.trim();

  // Try to get diff against the remote tracking branch
  try {
    const { stdout: diff } = await execAsync(
      `git diff origin/${currentBranch}...HEAD`,
      { maxBuffer: 1024 * 1024 * 10 }
    );
    if (diff.trim()) return diff;
  } catch {
    // Remote branch might not exist yet (first push)
  }

  // Fallback: diff of the last commit
  try {
    const { stdout: diff } = await execAsync("git diff HEAD~1...HEAD", {
      maxBuffer: 1024 * 1024 * 10,
    });
    return diff;
  } catch {
    // Only one commit in repo — diff all files
    const { stdout: diff } = await execAsync("git diff --cached HEAD", {
      maxBuffer: 1024 * 1024 * 10,
    });
    return diff;
  }
}

/**
 * Resolve paths to the bundled orchestrator and dashboard.
 * Same logic as start.ts — finds packages whether installed as npm or in monorepo.
 */
function resolvePaths(): { orchestratorDir: string; dashboardDir: string } {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);

  // In published package: dist/commands/review.js → ../../orchestrator/
  const pkgOrchestratorDir = join(__dirname, "..", "..", "orchestrator");
  // In monorepo dev: packages/cli/src/commands/ → packages/orchestrator/
  const devOrchestratorDir = join(__dirname, "..", "..", "..", "..", "orchestrator");

  const orchestratorDir = existsSync(join(pkgOrchestratorDir, "app"))
    ? pkgOrchestratorDir
    : existsSync(join(devOrchestratorDir, "app"))
      ? devOrchestratorDir
      : null;

  // Dashboard
  const pkgDashboardDir = join(__dirname, "..", "..", "dashboard");
  const devDashboardDir = join(__dirname, "..", "..", "..", "..", "dashboard");

  const dashboardDir = existsSync(pkgDashboardDir)
    ? pkgDashboardDir
    : existsSync(devDashboardDir)
      ? devDashboardDir
      : null;

  if (!orchestratorDir) {
    throw new Error(
      "Could not find the orchestrator package. " +
      "Make sure you're running from a Pulse project or the package is installed correctly."
    );
  }

  return {
    orchestratorDir,
    dashboardDir: dashboardDir || "",
  };
}

/**
 * Auto-start the orchestrator + dashboard in the background.
 * Reuses the same startup logic as `pulse start`.
 */
async function autoStartPulse(
  projectRoot: string,
  orchestratorPort: number,
  dashboardPort: number
): Promise<void> {
  const paths = resolvePaths();

  // Set up Python venv
  const venvPath = await ensureVenv(projectRoot);

  // Install dependencies
  const requirementsPath = join(paths.orchestratorDir, "requirements.txt");
  await installDeps(venvPath, requirementsPath);

  // Spawn options
  const spawnOpts: SpawnOptions = {
    orchestratorPort,
    dashboardPort,
    venvPath,
    orchestratorDir: paths.orchestratorDir,
    dashboardDir: paths.dashboardDir,
  };

  // Start orchestrator
  const orchestrator = spawnOrchestrator(spawnOpts);
  orchestrator.on("error", () => {});

  // Wait for orchestrator to be healthy
  const orchestratorHealthy = await waitForHealthy(
    `http://localhost:${orchestratorPort}/health`,
    30_000
  );

  if (!orchestratorHealthy) {
    throw new Error("Orchestrator failed to start (health check timed out)");
  }

  // Start dashboard
  let dashboard: ChildProcess | null = null;
  if (paths.dashboardDir) {
    dashboard = spawnDashboard(spawnOpts);
    dashboard.on("error", () => {});

    await waitForHealthy(
      `http://localhost:${dashboardPort}`,
      30_000
    );
  }

  // Write PID file so `pulse stop` can find them
  await writePidFile(projectRoot, {
    orchestratorPid: orchestrator.pid!,
    dashboardPid: dashboard?.pid,
    startedAt: new Date().toISOString(),
  });

  // Detach — let processes continue running after this CLI exits
  orchestrator.unref();
  if (dashboard) dashboard.unref();
}

/**
 * Open a URL in the default browser (cross-platform).
 */
async function openBrowser(url: string): Promise<void> {
  const { platform } = process;

  let command: string;
  if (platform === "darwin") {
    command = `open "${url}"`;
  } else if (platform === "win32") {
    command = `start "" "${url}"`;
  } else {
    command = `xdg-open "${url}"`;
  }

  await execAsync(command);
}

/**
 * Asynchronous prompt that reads from process.stdin.
 * In Git hooks, process.stdin is often disconnected. The hook script MUST
 * use `exec < /dev/tty` for this to work correctly.
 */
async function askQuestion(query: string, defaultYes = true): Promise<boolean> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    let answered = false;
    const promptText = "  " + PULSE_CYAN("?") + " " + chalk.bold.white(query) + (defaultYes ? PULSE_DIM(" (Y/n) ") : PULSE_DIM(" (y/N) "));
    
    rl.question(promptText, (answer) => {
      answered = true;
      rl.close();
      const ans = answer.trim().toLowerCase();
      if (ans === "") resolve(defaultYes);
      else resolve(ans === "y" || ans === "yes");
    });

    // If stdin closes (e.g. no tty available), fallback to default
    rl.on("close", () => {
      if (!answered) {
        process.stdout.write("\n");
        resolve(defaultYes);
      }
    });
  });
}
