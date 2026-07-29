/**
 * Pulse CLI — Child Process Management
 *
 * Manages the orchestrator (uvicorn) and dashboard (Next.js standalone)
 * as child processes. Handles spawning, PID tracking, health polling,
 * and graceful shutdown.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { readFile, writeFile, unlink, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import treeKill from "tree-kill";
import { getVenvBin } from "./python.js";
import { prefixStream } from "./ui.js";
import chalk from "chalk";

// ─── Types ───

export interface PidInfo {
  orchestratorPid: number;
  dashboardPid?: number;
  startedAt: string;
}

export interface SpawnOptions {
  orchestratorPort: number;
  dashboardPort: number;
  venvPath: string;
  orchestratorDir: string;
  dashboardDir: string;
}

// ─── Spawn Orchestrator ───

/**
 * Start the Python orchestrator via uvicorn from the venv.
 */
export function spawnOrchestrator(opts: SpawnOptions): ChildProcess {
  const uvicorn = getVenvBin(opts.venvPath, "uvicorn");

  const child = spawn(
    uvicorn,
    [
      "app.main:app",
      "--host", "0.0.0.0",
      "--port", String(opts.orchestratorPort),
    ],
    {
      cwd: opts.orchestratorDir,
      stdio: ["ignore", "pipe", "pipe"],
      // On Windows, we need shell: false to use the venv binary directly
      env: {
        ...process.env,
        PULSE_PROJECT_ROOT: process.cwd(),
        // Ensure the venv's Python is used
        VIRTUAL_ENV: opts.venvPath,
        PATH: join(opts.venvPath, process.platform === "win32" ? "Scripts" : "bin") +
          (process.platform === "win32" ? ";" : ":") +
          (process.env.PATH || ""),
      },
    }
  );

  prefixStream(child.stdout, "orchestrator", chalk.cyan);
  prefixStream(child.stderr, "orchestrator", chalk.cyan);

  return child;
}

// ─── Spawn Dashboard ───

/**
 * Start the pre-built Next.js dashboard in standalone mode.
 */
export function spawnDashboard(opts: SpawnOptions): ChildProcess {
  const standaloneRootServer = join(opts.dashboardDir, "server.js");
  const standaloneNextServer = join(opts.dashboardDir, ".next", "standalone", "server.js");
  const standaloneMonorepoServer = join(
    opts.dashboardDir,
    ".next",
    "standalone",
    "packages",
    "dashboard",
    "server.js"
  );

  let serverPath: string | null = null;
  if (existsSync(standaloneRootServer)) {
    serverPath = standaloneRootServer;
  } else if (existsSync(standaloneNextServer)) {
    serverPath = standaloneNextServer;
  } else if (existsSync(standaloneMonorepoServer)) {
    serverPath = standaloneMonorepoServer;
  }

  const useStandalone = Boolean(serverPath);

  let child: ChildProcess;

  if (useStandalone && serverPath) {
    const cwdDir = dirname(serverPath);
    child = spawn("node", [serverPath], {
      cwd: cwdDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PORT: String(opts.dashboardPort),
        HOSTNAME: "0.0.0.0",
      },
    });
  } else {
    // Fallback: run `npx next start` from the dashboard directory
    const npx = process.platform === "win32" ? "npx.cmd" : "npx";
    child = spawn(npx, ["next", "start", "-p", String(opts.dashboardPort)], {
      cwd: opts.dashboardDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env },
      shell: process.platform === "win32",
    });
  }

  prefixStream(child.stdout, "dashboard", chalk.magenta);
  prefixStream(child.stderr, "dashboard", chalk.magenta);

  return child;
}

// ─── PID File Management ───

function getPidFilePath(projectRoot: string): string {
  return join(projectRoot, ".pulse", ".pid.json");
}

/**
 * Write PID info so `pulse stop` can find running processes.
 */
export async function writePidFile(
  projectRoot: string,
  info: PidInfo
): Promise<void> {
  const pidPath = getPidFilePath(projectRoot);
  await mkdir(dirname(pidPath), { recursive: true });
  await writeFile(pidPath, JSON.stringify(info, null, 2), "utf-8");
}

/**
 * Read PID info from the .pulse/.pid.json file.
 */
export async function readPidFile(
  projectRoot: string
): Promise<PidInfo | null> {
  const pidPath = getPidFilePath(projectRoot);

  if (!existsSync(pidPath)) {
    return null;
  }

  try {
    const content = await readFile(pidPath, "utf-8");
    return JSON.parse(content) as PidInfo;
  } catch {
    return null;
  }
}

/**
 * Clean up the PID file after shutdown.
 */
export async function removePidFile(projectRoot: string): Promise<void> {
  const pidPath = getPidFilePath(projectRoot);

  if (existsSync(pidPath)) {
    await unlink(pidPath);
  }
}

// ─── Process Killing ───

/**
 * Kill a process and all its children (cross-platform).
 */
export async function killProcessTree(pid: number): Promise<void> {
  return new Promise((resolve, reject) => {
    treeKill(pid, "SIGTERM", (err) => {
      if (err) {
        // Process might already be dead — that's fine
        resolve();
      } else {
        resolve();
      }
    });
  });
}

// ─── Health Polling ───

/**
 * Poll a URL until it returns a successful response.
 * Used to wait for the orchestrator and dashboard to be ready.
 *
 * @param url - URL to poll
 * @param timeoutMs - Maximum time to wait (default: 30 seconds)
 * @param intervalMs - Time between polls (default: 500ms)
 * @returns true if healthy, false if timed out
 */
export async function waitForHealthy(
  url: string,
  timeoutMs: number = 30_000,
  intervalMs: number = 500
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return true;
      }
    } catch {
      // Server not ready yet — keep polling
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  return false;
}
