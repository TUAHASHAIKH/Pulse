/**
 * Pulse CLI — `pulse status`
 *
 * Quick health check showing the state of all Pulse components:
 * orchestrator, dashboard, Docker, and configuration.
 */

import { exec } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  printBanner,
  printStatusTable,
  printInfo,
} from "../utils/ui.js";

const execAsync = promisify(exec);

// ─── Status Command ───

export async function statusCommand(options: {
  port?: number;
  dashboardPort?: number;
}): Promise<void> {
  const orchestratorPort = options.port || 8000;
  const dashboardPort = options.dashboardPort || 3000;
  const projectRoot = process.cwd();

  printBanner();

  const items: { label: string; status: string; detail?: string }[] = [];

  // 1. Check orchestrator
  try {
    const res = await fetch(`http://localhost:${orchestratorPort}/health`);
    const data = await res.json() as {
      status: string;
      version: string;
      uptime_seconds: number;
    };

    const uptime = formatUptime(data.uptime_seconds);
    items.push({
      label: "Orchestrator",
      status: "running",
      detail: `:${orchestratorPort}  (uptime: ${uptime})`,
    });
  } catch {
    items.push({
      label: "Orchestrator",
      status: "stopped",
      detail: "Not running",
    });
  }

  // 2. Check dashboard
  try {
    const res = await fetch(`http://localhost:${dashboardPort}`);
    if (res.ok || res.status === 304) {
      items.push({
        label: "Dashboard",
        status: "running",
        detail: `:${dashboardPort}`,
      });
    } else {
      throw new Error("not ok");
    }
  } catch {
    items.push({
      label: "Dashboard",
      status: "stopped",
      detail: "Not running",
    });
  }

  // 3. Check Docker
  try {
    await execAsync("docker info");
    items.push({
      label: "Docker",
      status: "running",
      detail: "Available (repair agent enabled)",
    });
  } catch {
    items.push({
      label: "Docker",
      status: "warning",
      detail: "Not found (repair agent disabled)",
    });
  }

  // 4. Check config
  const configPath = join(projectRoot, ".pulse", "config.json");
  if (existsSync(configPath)) {
    items.push({
      label: "Config",
      status: "running",
      detail: ".pulse/config.json ✓",
    });
  } else {
    items.push({
      label: "Config",
      status: "warning",
      detail: 'Not found — run "pulse init"',
    });
  }

  printStatusTable(items);
}

// ─── Helpers ───

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}
