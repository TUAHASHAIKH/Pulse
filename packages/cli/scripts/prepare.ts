/**
 * Pulse CLI — Prepare Script
 *
 * Bundles the orchestrator and dashboard into the CLI package
 * so that `npm publish` creates a self-contained package.
 *
 * This script:
 *   1. Builds the dashboard (next build → standalone output)
 *   2. Copies the orchestrator source + requirements into cli/orchestrator/
 *   3. Copies the dashboard standalone build into cli/dashboard/
 *   4. Compiles the CLI TypeScript
 *
 * Run with: node scripts/prepare.js
 */

import { execSync } from "node:child_process";
import { cpSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const CLI_ROOT = join(__dirname, "..");
const PACKAGES_ROOT = join(CLI_ROOT, "..");
const ORCHESTRATOR_ROOT = join(PACKAGES_ROOT, "orchestrator");
const DASHBOARD_ROOT = join(PACKAGES_ROOT, "dashboard");

function log(msg: string) {
  console.log(`\n  📦 ${msg}`);
}

function run(cmd: string, cwd: string) {
  console.log(`     > ${cmd}`);
  execSync(cmd, {
    cwd,
    stdio: "inherit",
    env: { ...process.env, NODE_OPTIONS: "--max-old-space-size=4096" },
  });
}

// ─── 1. Build the Dashboard (if needed) ───

const nextDir = join(DASHBOARD_ROOT, ".next");
if (!existsSync(nextDir)) {
  log("Building dashboard...");
  run("npm run build", DASHBOARD_ROOT);
} else {
  log("Dashboard build (.next) found — skipping rebuild");
}

// ─── 2. Copy Orchestrator Into CLI Package ───

log("Bundling orchestrator...");

const orchDest = join(CLI_ROOT, "orchestrator");

// Clean previous bundle
if (existsSync(orchDest)) {
  rmSync(orchDest, { recursive: true, force: true });
}
mkdirSync(orchDest, { recursive: true });

// Copy the app/ directory (Python source)
cpSync(join(ORCHESTRATOR_ROOT, "app"), join(orchDest, "app"), {
  recursive: true,
  filter: (src) => {
    // Skip __pycache__, .pyc files, and .venv
    if (src.includes("__pycache__")) return false;
    if (src.endsWith(".pyc")) return false;
    if (src.includes(".venv")) return false;
    return true;
  },
});

// Copy requirements.txt
cpSync(
  join(ORCHESTRATOR_ROOT, "requirements.txt"),
  join(orchDest, "requirements.txt")
);

log("Orchestrator bundled ✓");

// ─── 3. Copy Dashboard Standalone Build Into CLI Package ───

log("Bundling dashboard...");

const dashDest = join(CLI_ROOT, "dashboard");

// Clean previous bundle
if (existsSync(dashDest)) {
  rmSync(dashDest, { recursive: true, force: true });
}
mkdirSync(dashDest, { recursive: true });

const standaloneSrc = join(DASHBOARD_ROOT, ".next", "standalone");
const staticSrc = join(DASHBOARD_ROOT, ".next", "static");
const publicSrc = join(DASHBOARD_ROOT, "public");

if (existsSync(standaloneSrc)) {
  // Copy standalone server
  cpSync(standaloneSrc, dashDest, { recursive: true });

  // Copy static assets (Next.js requires these alongside standalone)
  if (existsSync(staticSrc)) {
    cpSync(staticSrc, join(dashDest, ".next", "static"), { recursive: true });
  }

  // Copy public assets
  if (existsSync(publicSrc)) {
    cpSync(publicSrc, join(dashDest, "public"), { recursive: true });
  }

  log("Dashboard bundled (standalone) ✓");
} else {
  // Fallback: copy the dashboard with .next for `next start`
  log("⚠ Standalone build not found — copying full dashboard with .next");

  cpSync(DASHBOARD_ROOT, dashDest, {
    recursive: true,
    filter: (src) => {
      if (src.includes("node_modules")) return false;
      if (src.includes("cache")) return false;
      if (src.endsWith(".gitignore")) return false;
      return true;
    },
  });
}

// ─── 4. Build CLI TypeScript ───

log("Compiling CLI TypeScript...");
run("npm run build", CLI_ROOT);

// ─── Done ───

log("Package ready for publishing! 🎉");
console.log("\n  To publish:");
console.log("    cd packages/cli");
console.log("    npm publish\n");
