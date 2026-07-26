/**
 * Pulse CLI — System Prerequisite Checks
 *
 * Validates that everything needed to run Pulse is available
 * before attempting to start. Provides clear, actionable errors.
 */

import { exec } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";
import { join } from "node:path";
import net from "node:net";
import { findPython } from "./python.js";
import { printSuccess, printWarning, printError } from "./ui.js";

const execAsync = promisify(exec);

// ─── Individual Checks ───

/**
 * Check that Python 3.11+ is installed and accessible.
 */
export async function checkPython(): Promise<boolean> {
  try {
    const pythonCmd = await findPython();
    const { stdout } = await execAsync(
      `${pythonCmd} -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"`
    );
    printSuccess(`Python ${stdout.trim()} found`);
    return true;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    printError(message);
    return false;
  }
}

/**
 * Check that Docker is installed and the daemon is running.
 * This is optional — Pulse works without Docker (repair agent is just disabled).
 */
export async function checkDocker(): Promise<boolean> {
  try {
    await execAsync("docker info");
    printSuccess("Docker is available");
    return true;
  } catch {
    printWarning(
      "Docker not found — the Repair Agent will be disabled.\n" +
      "           Install Docker Desktop from: https://www.docker.com/products/docker-desktop/"
    );
    return false;
  }
}

/**
 * Check that a TCP port is available (not in use).
 */
export async function checkPort(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();

    server.once("error", (err: NodeJS.ErrnoException) => {
      if (err.code === "EADDRINUSE") {
        printError(`Port ${port} is already in use`);
        resolve(false);
      } else {
        // Some other error — treat as available
        resolve(true);
      }
    });

    server.once("listening", () => {
      server.close();
      resolve(true);
    });

    server.listen(port, "127.0.0.1");
  });
}

/**
 * Check that .pulse/config.json exists in the project root.
 */
export function checkConfig(projectRoot: string): boolean {
  const configPath = join(projectRoot, ".pulse", "config.json");

  if (existsSync(configPath)) {
    printSuccess("Configuration found (.pulse/config.json)");
    return true;
  } else {
    printWarning(
      'No configuration found. Run "pulse init" to set up your API keys.'
    );
    return false;
  }
}

// ─── Run All Checks ───

export interface PrereqResult {
  python: boolean;
  docker: boolean;
  orchestratorPort: boolean;
  dashboardPort: boolean;
  config: boolean;
}

/**
 * Run all prerequisite checks and print a summary.
 *
 * @returns Object with pass/fail status for each check.
 *          Only `python` is a hard requirement.
 */
export async function runAllChecks(
  projectRoot: string,
  orchestratorPort: number,
  dashboardPort: number
): Promise<PrereqResult> {
  console.log();

  const python = await checkPython();
  const docker = await checkDocker();

  const orchestratorPortOk = await checkPort(orchestratorPort);
  if (orchestratorPortOk) {
    printSuccess(`Port ${orchestratorPort} is available (orchestrator)`);
  }

  const dashboardPortOk = await checkPort(dashboardPort);
  if (dashboardPortOk) {
    printSuccess(`Port ${dashboardPort} is available (dashboard)`);
  }

  const config = checkConfig(projectRoot);

  console.log();

  return {
    python,
    docker,
    orchestratorPort: orchestratorPortOk,
    dashboardPort: dashboardPortOk,
    config,
  };
}
