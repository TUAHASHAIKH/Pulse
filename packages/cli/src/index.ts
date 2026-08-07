#!/usr/bin/env node

/**
 * Pulse CLI — Entry Point
 *
 * The single command that makes Pulse a developer tool:
 *
 *   pulse start    → boots orchestrator + dashboard
 *   pulse init     → interactive setup wizard
 *   pulse review   → trigger a review from the terminal
 *   pulse stop     → graceful shutdown
 *   pulse status   → health check
 *
 * Install globally:  npm i -g pulseai
 * Or use directly:   npx pulseai start
 */

import { Command } from "commander";
import { startCommand } from "./commands/start.js";
import { initCommand } from "./commands/init.js";
import { reviewCommand } from "./commands/review.js";
import { stopCommand } from "./commands/stop.js";
import { statusCommand } from "./commands/status.js";
import { getCliVersion } from "./utils/version.js";

const program = new Command();

program
  .name("pulse")
  .description(
    "🫀 Pulse — AI-powered code review from your terminal.\n" +
    "Security, performance, and quality agents on every PR."
  )
  .version(getCliVersion());

// ─── pulse start ───

program
  .command("start")
  .description("Start the Pulse orchestrator and dashboard")
  .option("-p, --port <port>", "Orchestrator port", "8000")
  .option("-d, --dashboard-port <port>", "Dashboard port", "3000")
  .option("--no-dashboard", "Start orchestrator only (no dashboard)")
  .action(async (opts) => {
    await startCommand({
      port: parseInt(opts.port, 10),
      dashboardPort: parseInt(opts.dashboardPort, 10),
      noDashboard: opts.dashboard === false,
    });
  });

// ─── pulse init ───

program
  .command("init")
  .description("Set up Pulse for this project (interactive wizard)")
  .option("--force", "Overwrite existing configuration")
  .action(async (opts) => {
    await initCommand({ force: opts.force });
  });

// ─── pulse review ───

program
  .command("review")
  .description("Trigger a code review")
  .option("--pr <ref>", "Review a GitHub PR (format: owner/repo#123)")
  .option("--all", "Full repository audit — scan all source files, not just git diff")
  .option("--force", "Re-scan all files even if unchanged since last audit (use with --all)")
  .option("-p, --port <port>", "Orchestrator port", "8000")
  .action(async (opts) => {
    await reviewCommand({
      pr: opts.pr,
      port: parseInt(opts.port, 10),
      all: opts.all,
      force: opts.force,
    });
  });

// ─── pulse stop ───

program
  .command("stop")
  .description("Stop all running Pulse processes")
  .action(async () => {
    await stopCommand();
  });

// ─── pulse status ───

program
  .command("status")
  .description("Check the status of Pulse components")
  .option("-p, --port <port>", "Orchestrator port", "8000")
  .option("-d, --dashboard-port <port>", "Dashboard port", "3000")
  .action(async (opts) => {
    await statusCommand({
      port: parseInt(opts.port, 10),
      dashboardPort: parseInt(opts.dashboardPort, 10),
    });
  });

// ─── Parse & Run ───

program.parse();
