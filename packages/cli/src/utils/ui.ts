/**
 * Pulse CLI — Terminal UI Helpers
 *
 * Branded output, spinners, and colored log prefixes.
 * Keeps all the visual polish in one place so commands stay clean.
 */

import chalk from "chalk";
import ora, { type Ora } from "ora";
import { Readable } from "node:stream";
import { createInterface } from "node:readline";

import { getCliVersion } from "./version.js";

// ─── Brand Colors ───

const CYAN = chalk.hex("#00F0FF");
const DIM = chalk.dim;
const BOLD = chalk.bold;

// ─── Banner ───

export function printBanner(version: string = getCliVersion()): void {
  console.log();
  console.log(CYAN.bold("  🫀 Pulse") + DIM(` v${version}`));
  console.log(DIM("  ─────────────────────────────────────"));
  console.log(DIM("  AI-powered code review from your terminal"));
  console.log();
}

// ─── Status Messages ───

export function printSuccess(msg: string): void {
  console.log(chalk.green("  ✓ ") + msg);
}

export function printWarning(msg: string): void {
  console.log(chalk.yellow("  ⚠ ") + msg);
}

export function printError(msg: string): void {
  console.log(chalk.red("  ✗ ") + msg);
}

export function printInfo(msg: string): void {
  console.log(DIM("  ℹ ") + msg);
}

// ─── Spinners ───

export function createSpinner(text: string): Ora {
  return ora({
    text,
    color: "cyan",
    indent: 2,
  });
}

// ─── URL Display ───

export function printUrls(orchestratorPort: number, dashboardPort: number): void {
  console.log();
  console.log(CYAN.bold("  🫀 Pulse is running!"));
  console.log(DIM("  ─────────────────────────────────────"));
  console.log(
    `  ${BOLD("Orchestrator")}  → ${chalk.underline(`http://localhost:${orchestratorPort}`)}`
  );
  console.log(
    `  ${BOLD("Dashboard")}     → ${chalk.underline(`http://localhost:${dashboardPort}`)}`
  );
  console.log(
    `  ${BOLD("API Docs")}      → ${chalk.underline(`http://localhost:${orchestratorPort}/docs`)}`
  );
  console.log();
  console.log(DIM("  Press Ctrl+C to stop"));
  console.log();
}

// ─── Prefixed Stream Output ───

/**
 * Pipe a child process stdout/stderr with a colored prefix.
 * e.g. "[orchestrator] Starting server on port 8000"
 */
export function prefixStream(
  stream: Readable | null,
  prefix: string,
  color: typeof chalk.red
): void {
  if (!stream) return;

  const rl = createInterface({ input: stream });
  const tag = color(`  [${prefix}] `);

  rl.on("line", (line) => {
    console.log(tag + DIM(line));
  });
}

// ─── Status Table ───

export function printStatusTable(items: { label: string; status: string; detail?: string }[]): void {
  console.log();
  console.log(CYAN.bold("  🫀 Pulse Status"));
  console.log(DIM("  ─────────────────────────────────────"));

  for (const item of items) {
    const statusIcon =
      item.status === "running"
        ? chalk.green("●")
        : item.status === "warning"
          ? chalk.yellow("●")
          : chalk.red("●");

    const detail = item.detail ? DIM(` ${item.detail}`) : "";
    console.log(`  ${statusIcon} ${BOLD(item.label.padEnd(16))}${detail}`);
  }

  console.log();
}
