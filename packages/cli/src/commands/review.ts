/**
 * Pulse CLI — `pulse review`
 *
 * Trigger a code review from the terminal.
 *   - `pulse review`              → sends `git diff HEAD` to the orchestrator
 *   - `pulse review --pr org/repo#42` → sends the PR reference
 */

import { exec } from "node:child_process";
import { promisify } from "node:util";
import chalk from "chalk";
import {
  printBanner,
  printSuccess,
  printError,
  printInfo,
  createSpinner,
} from "../utils/ui.js";

const execAsync = promisify(exec);

// ─── Review Command ───

export async function reviewCommand(options: {
  pr?: string;
  port?: number;
}): Promise<void> {
  const orchestratorPort = options.port || 8000;
  const baseUrl = `http://localhost:${orchestratorPort}`;

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

  // 2. Build the review payload
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
    body = { repo, pr_number: parseInt(prNumber, 10) };
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
        process.exit(1);
      }

      body = { diff };
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
    console.log();
    const results = data.results || [];

    if (results.length === 0) {
      printSuccess("No findings — your code looks good! 🎉");
      return;
    }

    for (const agentResult of results) {
      console.log(chalk.bold(`  📋 ${agentResult.agent_name}`));

      if (agentResult.findings.length === 0) {
        console.log(chalk.dim("     No findings"));
        continue;
      }

      for (const finding of agentResult.findings) {
        const severityColor =
          finding.severity === "critical"
            ? chalk.red
            : finding.severity === "warning"
              ? chalk.yellow
              : chalk.blue;

        const severity = severityColor(
          `[${finding.severity.toUpperCase()}]`
        );

        console.log(`     ${severity} ${finding.title}`);
        console.log(chalk.dim(`           ${finding.file}`));
        console.log(chalk.dim(`           ${finding.description}`));
        console.log();
      }
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    reviewSpinner.fail(`Review request failed: ${message}`);
    process.exit(1);
  }
}
