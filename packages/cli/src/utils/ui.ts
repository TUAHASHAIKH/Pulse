/**
 * Pulse CLI — Terminal UI Design System
 *
 * Premium, branded terminal output with consistent styling.
 * All visual output flows through this module.
 */

import chalk from "chalk";
import ora, { type Ora } from "ora";
import { Readable } from "node:stream";
import { createInterface } from "node:readline";

import { getCliVersion } from "./version.js";

// ─── Brand Palette ───

const PULSE_CYAN    = chalk.hex("#00F0FF");
const PULSE_MAGENTA = chalk.hex("#FF006E");
const PULSE_GREEN   = chalk.hex("#39FF14");
const PULSE_AMBER   = chalk.hex("#FFB800");
const PULSE_RED     = chalk.hex("#FF3B30");
const PULSE_DIM     = chalk.hex("#555555");
const PULSE_GRAY    = chalk.hex("#888888");
const PULSE_WHITE   = chalk.hex("#E0E0E0");

// ─── Box Drawing ───

const BOX = {
  tl: "┌", tr: "┐", bl: "└", br: "┘",
  h: "─", v: "│",
  ltee: "├", rtee: "┤",
};

function boxLine(width: number): string {
  return BOX.h.repeat(width);
}

function boxTop(title: string, width: number): string {
  const inner = width - title.length - 4;
  return PULSE_DIM(BOX.tl + BOX.h + " ") + PULSE_CYAN.bold(title) + PULSE_DIM(" " + boxLine(Math.max(inner, 0)) + BOX.tr);
}

function boxBottom(width: number): string {
  return PULSE_DIM(BOX.bl + boxLine(width) + BOX.br);
}

function boxMid(width: number): string {
  return PULSE_DIM(BOX.ltee + boxLine(width) + BOX.rtee);
}

function boxRow(content: string, width: number): string {
  // content is already styled, so we just pad with the box borders
  return PULSE_DIM(BOX.v) + " " + content;
}

// ─── ASCII Logo ───

const LOGO_LINES = [
  "  ██████  ██    ██ ██      ███████ ███████ ",
  "  ██   ██ ██    ██ ██      ██      ██      ",
  "  ██████  ██    ██ ██      ███████ █████   ",
  "  ██      ██    ██ ██           ██ ██      ",
  "  ██       ██████  ███████ ███████ ███████ ",
];

// ─── Banners ───

export function printBanner(version: string = getCliVersion()): void {
  console.log();
  
  // Print gradient logo
  for (const line of LOGO_LINES) {
    console.log(PULSE_CYAN(line));
  }
  
  console.log();
  console.log(
    "  " + PULSE_CYAN("🫀") + " " +
    chalk.bold.white("Pulse") + " " +
    PULSE_DIM("v" + version) + "  " +
    PULSE_DIM("│") + "  " +
    PULSE_GRAY("AI-Powered Code Review")
  );
  console.log(PULSE_DIM("  " + "─".repeat(48)));
  console.log();
}

export function printCompactBanner(subtitle: string): void {
  console.log();
  console.log(
    "  " + PULSE_CYAN("🫀") + " " +
    chalk.bold.white("Pulse") + PULSE_DIM(" ›") + " " +
    PULSE_CYAN.bold(subtitle)
  );
  console.log(PULSE_DIM("  " + "─".repeat(48)));
}

// ─── Section Headers ───

export function printSectionHeader(title: string): void {
  console.log();
  console.log("  " + PULSE_CYAN("▸") + " " + chalk.bold.white(title));
  console.log(PULSE_DIM("  " + "─".repeat(48)));
}

// ─── Status Messages ───

export function printSuccess(msg: string): void {
  console.log("  " + PULSE_GREEN("✔") + "  " + msg);
}

export function printWarning(msg: string): void {
  console.log("  " + PULSE_AMBER("⚠") + "  " + msg);
}

export function printError(msg: string): void {
  console.log("  " + PULSE_RED("✖") + "  " + msg);
}

export function printInfo(msg: string): void {
  console.log("  " + PULSE_DIM("›") + "  " + PULSE_GRAY(msg));
}

export function printStep(step: number, total: number, msg: string): void {
  const badge = PULSE_DIM(`[${step}/${total}]`);
  console.log(`  ${badge}  ${msg}`);
}

// ─── Key-Value Display ───

export function printKeyValue(key: string, value: string, keyWidth = 18): void {
  console.log(
    "  " + PULSE_DIM(BOX.v) + "  " +
    PULSE_GRAY(key.padEnd(keyWidth)) +
    chalk.white(value)
  );
}

// ─── Boxed Info Panel ───

export function printInfoBox(title: string, lines: { key: string; value: string; color?: "green" | "amber" | "red" | "cyan" | "dim" }[]): void {
  const width = 50;
  console.log();
  console.log("  " + boxTop(title, width));
  
  for (const line of lines) {
    const colorFn = line.color === "green" ? PULSE_GREEN
      : line.color === "amber" ? PULSE_AMBER
      : line.color === "red" ? PULSE_RED
      : line.color === "cyan" ? PULSE_CYAN
      : PULSE_WHITE;
    
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      PULSE_GRAY(line.key.padEnd(16)) +
      colorFn(line.value)
    );
  }
  
  console.log("  " + boxBottom(width));
}

// ─── Spinners ───

export function createSpinner(text: string): Ora {
  return ora({
    text,
    color: "cyan",
    indent: 2,
    prefixText: "",
    spinner: "dots",
  });
}

// ─── URL Display ───

export function printUrls(orchestratorPort: number, dashboardPort: number): void {
  printInfoBox("PULSE ACTIVE", [
    { key: "Orchestrator", value: `http://localhost:${orchestratorPort}`, color: "cyan" },
    { key: "Dashboard", value: `http://localhost:${dashboardPort}`, color: "cyan" },
    { key: "API Docs", value: `http://localhost:${orchestratorPort}/docs`, color: "dim" },
  ]);
  
  console.log();
  printInfo("Press Ctrl+C to stop all services");
  console.log();
}

// ─── Prefixed Stream Output ───

/**
 * Pipe a child process stdout/stderr with a colored prefix.
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
    console.log(tag + PULSE_DIM(line));
  });
}

// ─── Status Table ───

export function printStatusTable(items: { label: string; status: string; detail?: string }[]): void {
  const width = 50;

  console.log();
  console.log("  " + boxTop("SYSTEM STATUS", width));

  for (const item of items) {
    const dot =
      item.status === "running"
        ? PULSE_GREEN("●")
        : item.status === "warning"
          ? PULSE_AMBER("●")
          : PULSE_RED("●");

    const statusText =
      item.status === "running"
        ? PULSE_GREEN("ONLINE")
        : item.status === "warning"
          ? PULSE_AMBER("WARN")
          : PULSE_RED("OFFLINE");

    const detail = item.detail ? PULSE_DIM(` ${item.detail}`) : "";

    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      dot + " " +
      chalk.bold.white(item.label.padEnd(14)) +
      statusText.padEnd(20) +
      detail
    );
  }

  console.log("  " + boxBottom(width));
  console.log();
}

// ─── Review Summary Box ───

export function printReviewSummary(
  findings: { label: string; count: number; icon: string }[],
  repairs: number,
  totalFindings: number,
  severity: { critical: number; warning: number; info: number }
): void {
  const width = 50;

  console.log();
  console.log("  " + boxTop("REVIEW RESULTS", width));

  // Per-agent rows
  for (const f of findings) {
    const countColor = f.count === 0 ? PULSE_GREEN : PULSE_AMBER;
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      f.icon + " " +
      PULSE_GRAY(f.label.padEnd(16)) +
      countColor(`${f.count} issue${f.count !== 1 ? "s" : ""}`)
    );
  }

  // Repairs
  if (repairs > 0) {
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      "🔧 " +
      PULSE_GRAY("Repair Agent".padEnd(16)) +
      PULSE_CYAN(`${repairs} fix${repairs !== 1 ? "es" : ""} generated`)
    );
  }

  // Divider
  console.log("  " + boxMid(width));

  // Totals
  if (totalFindings === 0) {
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      PULSE_GREEN("✔  No issues found — your code looks great! 🎉")
    );
  } else {
    const parts: string[] = [];
    if (severity.critical) parts.push(PULSE_RED(`${severity.critical} critical`));
    if (severity.warning) parts.push(PULSE_AMBER(`${severity.warning} warning`));
    if (severity.info) parts.push(chalk.blue(`${severity.info} info`));

    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      chalk.bold.white(`📋 ${totalFindings} total`) + PULSE_DIM("  ") +
      parts.join(PULSE_DIM(" · "))
    );
  }

  console.log("  " + boxBottom(width));
}

// ─── Guidance Box (for push review) ───

export function printGuidanceBox(steps: string[]): void {
  const width = 50;

  console.log();
  console.log("  " + boxTop("NEXT STEPS", width));

  for (let i = 0; i < steps.length; i++) {
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      PULSE_CYAN.bold(`${i + 1}.`) + " " +
      steps[i]
    );
  }

  console.log("  " + boxBottom(width));
  console.log();
}

// ─── Prereq Check Table ───

export function printPrereqLine(passed: boolean, label: string, detail?: string): void {
  const icon = passed ? PULSE_GREEN("✔") : PULSE_RED("✖");
  const detailStr = detail ? PULSE_DIM(` — ${detail}`) : "";
  console.log(`  ${icon}  ${label}${detailStr}`);
}

// ─── Shutdown Message ───

export function printShutdown(): void {
  console.log();
  console.log("  " + PULSE_CYAN("🫀") + " " + chalk.bold.white("Pulse stopped.") + " " + PULSE_DIM("See you next time."));
  console.log();
}

// ─── Hook Status ───

export function printHookStatus(installed: boolean, managed: boolean): void {
  const width = 50;

  console.log();
  console.log("  " + boxTop("GIT HOOKS", width));

  if (!installed) {
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      PULSE_RED("●") + " " +
      chalk.white("Pre-push hook") + "  " +
      PULSE_DIM("not installed")
    );
  } else if (managed) {
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      PULSE_GREEN("●") + " " +
      chalk.white("Pre-push hook") + "  " +
      PULSE_GREEN("active")
    );
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      PULSE_DIM("  Code will be reviewed before every push")
    );
  } else {
    console.log(
      "  " + PULSE_DIM(BOX.v) + "  " +
      PULSE_AMBER("●") + " " +
      chalk.white("Pre-push hook") + "  " +
      PULSE_AMBER("exists (not managed by Pulse)")
    );
  }

  console.log("  " + boxBottom(width));
  console.log();
}

// ─── Init Success ───

export function printInitSuccess(config: {
  wantsGitHub: boolean;
  wantsPushReview: boolean;
  webhookSecret: string;
}): void {
  printInfoBox("CONFIGURATION SAVED", [
    { key: "Config file", value: ".pulse/config.json", color: "green" },
    { key: "Push review", value: config.wantsPushReview ? "enabled" : "disabled", color: config.wantsPushReview ? "green" : "dim" },
    { key: "GitHub", value: config.wantsGitHub ? "configured" : "not configured", color: config.wantsGitHub ? "green" : "dim" },
  ]);

  console.log();
  printSectionHeader("Getting Started");
  console.log(`  ${PULSE_CYAN("1.")} Run  ${chalk.bold("pulse start")}`);
  console.log(`  ${PULSE_CYAN("2.")} Open ${chalk.bold.underline("http://localhost:3000")}`);

  if (config.wantsGitHub) {
    console.log();
    printSectionHeader("GitHub Webhook");
    console.log(`  ${PULSE_DIM("Repo → Settings → Webhooks → Add webhook")}`);
    console.log(`  ${PULSE_GRAY("Payload URL".padEnd(16))} ${chalk.white("http://YOUR_SERVER:8000/webhook/github")}`);
    console.log(`  ${PULSE_GRAY("Content type".padEnd(16))} ${chalk.white("application/json")}`);
    console.log(`  ${PULSE_GRAY("Secret".padEnd(16))} ${chalk.white(config.webhookSecret.slice(0, 8) + "...")}`);
    console.log(`  ${PULSE_GRAY("Events".padEnd(16))} ${chalk.white("Pull requests")}`);
  }

  if (config.wantsPushReview) {
    console.log();
    printSuccess("Git hook installed — code reviewed on every push");
    printInfo("Disable with: pulse hooks uninstall");
  }

  console.log();
}

// Re-export chalk colors for use in commands
export { PULSE_CYAN, PULSE_GREEN, PULSE_AMBER, PULSE_RED, PULSE_DIM, PULSE_GRAY, PULSE_WHITE, PULSE_MAGENTA };
