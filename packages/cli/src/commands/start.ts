/**
 * Pulse CLI — `pulse start`
 *
 * The core command. Boots the Python orchestrator and Next.js dashboard
 * with a single command. Manages venvs, dependencies, health checks,
 * and graceful shutdown.
 */

import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import type { ChildProcess } from "node:child_process";
import {
  printBanner,
  printUrls,
  printSuccess,
  printWarning,
  printError,
  printInfo,
  printStep,
  printShutdown,
  createSpinner,
  PULSE_DIM,
} from "../utils/ui.js";
import { ensureVenv, installDeps } from "../utils/python.js";
import { runAllChecks } from "../utils/prereqs.js";
import {
  spawnOrchestrator,
  spawnDashboard,
  writePidFile,
  removePidFile,
  killProcessTree,
  waitForHealthy,
  type SpawnOptions,
} from "../utils/process.js";

// ─── Resolve Bundled Paths ───

/**
 * When installed as an npm package, the orchestrator and dashboard
 * are bundled alongside the CLI at known relative paths.
 * When running in development, they're sibling packages in the monorepo.
 */
function resolvePaths(): { orchestratorDir: string; dashboardDir: string } {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);

  // In published package: dist/commands/start.js → ../../orchestrator/
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

// ─── Start Command ───

export async function startCommand(options: {
  port?: number;
  dashboardPort?: number;
  noDashboard?: boolean;
}): Promise<void> {
  const orchestratorPort = options.port || 8000;
  const dashboardPort = options.dashboardPort || 3000;
  const projectRoot = process.cwd();

  printBanner();

  // 1. Check prerequisites
  const checks = await runAllChecks(projectRoot, orchestratorPort, dashboardPort);

  if (!checks.python) {
    printError("Cannot start without Python 3.11+. Aborting.");
    process.exit(1);
  }

  if (!checks.orchestratorPort) {
    printError(`Port ${orchestratorPort} is in use. Use --port to specify a different port.`);
    process.exit(1);
  }

  if (!options.noDashboard && !checks.dashboardPort) {
    printError(
      `Port ${dashboardPort} is in use. Use --dashboard-port to specify a different port.`
    );
    process.exit(1);
  }

  // 2. Resolve paths to bundled orchestrator and dashboard
  const paths = resolvePaths();

  // 3. Set up Python venv
  const venvSpinner = createSpinner("Setting up Python environment...");
  venvSpinner.start();

  let venvPath: string;
  try {
    venvPath = await ensureVenv(projectRoot);
    venvSpinner.succeed("Python environment ready");
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    venvSpinner.fail(`Failed to create Python environment: ${message}`);
    process.exit(1);
  }

  // 4. Install dependencies
  const depsSpinner = createSpinner("Checking Python dependencies...");
  depsSpinner.start();

  try {
    const requirementsPath = join(paths.orchestratorDir, "requirements.txt");
    const installed = await installDeps(venvPath, requirementsPath);

    if (installed) {
      depsSpinner.succeed("Python dependencies installed");
    } else {
      depsSpinner.succeed("Python dependencies up to date");
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    depsSpinner.fail(`Failed to install dependencies: ${message}`);
    process.exit(1);
  }

  // 5. Spawn processes
  const spawnOpts: SpawnOptions = {
    orchestratorPort,
    dashboardPort,
    venvPath,
    orchestratorDir: paths.orchestratorDir,
    dashboardDir: paths.dashboardDir,
  };

  const orchestratorSpinner = createSpinner("Starting orchestrator...");
  orchestratorSpinner.start();

  const orchestrator = spawnOrchestrator(spawnOpts);

  orchestrator.on("error", (err) => {
    orchestratorSpinner.fail(`Orchestrator failed to start: ${err.message}`);
    process.exit(1);
  });

  // Wait for orchestrator to be healthy
  const orchestratorHealthy = await waitForHealthy(
    `http://localhost:${orchestratorPort}/health`,
    30_000
  );

  if (!orchestratorHealthy) {
    orchestratorSpinner.fail("Orchestrator failed to start (health check timed out)");
    await killProcessTree(orchestrator.pid!);
    process.exit(1);
  }

  orchestratorSpinner.succeed("Orchestrator is running");

  // Start dashboard (unless --no-dashboard)
  let dashboard: ChildProcess | null = null;

  if (!options.noDashboard && paths.dashboardDir) {
    const dashboardSpinner = createSpinner("Starting dashboard...");
    dashboardSpinner.start();

    dashboard = spawnDashboard(spawnOpts);

    dashboard.on("error", (err) => {
      dashboardSpinner.fail(`Dashboard failed to start: ${err.message}`);
      // Dashboard is optional — don't exit
    });

    const dashboardHealthy = await waitForHealthy(
      `http://localhost:${dashboardPort}`,
      30_000
    );

    if (dashboardHealthy) {
      dashboardSpinner.succeed("Dashboard is running");
    } else {
      dashboardSpinner.warn("Dashboard may not be ready yet (continuing anyway)");
    }
  } else if (!options.noDashboard) {
    printWarning("Dashboard not found — starting orchestrator only");
  }

  // 6. Write PID file
  await writePidFile(projectRoot, {
    orchestratorPid: orchestrator.pid!,
    dashboardPid: dashboard?.pid,
    startedAt: new Date().toISOString(),
  });

  // 7. Print success
  if (!options.noDashboard && paths.dashboardDir) {
    printUrls(orchestratorPort, dashboardPort);
  } else {
    console.log();
    printSuccess(`Orchestrator running at http://localhost:${orchestratorPort}`);
    printSuccess(`API docs at http://localhost:${orchestratorPort}/docs`);
    console.log();
  }

  // 8. Handle graceful shutdown
  const shutdown = async (signal: string) => {
    console.log();

    const spinner = createSpinner("Shutting down...");
    spinner.start();

    if (orchestrator.pid) await killProcessTree(orchestrator.pid);
    if (dashboard?.pid) await killProcessTree(dashboard.pid);

    await removePidFile(projectRoot);
    spinner.succeed("All processes terminated");
    printShutdown();
    process.exit(0);
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  // Keep the process alive
  orchestrator.on("exit", async (code) => {
    printError(`Orchestrator exited with code ${code}`);
    if (dashboard?.pid) await killProcessTree(dashboard.pid);
    await removePidFile(projectRoot);
    process.exit(code || 1);
  });
}
