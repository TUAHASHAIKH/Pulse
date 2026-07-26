/**
 * Pulse CLI — `pulse stop`
 *
 * Gracefully stop all running Pulse processes.
 * Reads PIDs from .pulse/.pid.json and sends SIGTERM.
 */

import {
  readPidFile,
  removePidFile,
  killProcessTree,
} from "../utils/process.js";
import {
  printBanner,
  printSuccess,
  printWarning,
  printError,
  createSpinner,
} from "../utils/ui.js";

// ─── Stop Command ───

export async function stopCommand(): Promise<void> {
  const projectRoot = process.cwd();

  printBanner("0.1.0");

  // 1. Read PID file
  const pidInfo = await readPidFile(projectRoot);

  if (!pidInfo) {
    printWarning("No running Pulse instance found (.pulse/.pid.json not found)");
    return;
  }

  // 2. Kill processes
  const spinner = createSpinner("Stopping Pulse...");
  spinner.start();

  try {
    // Kill orchestrator
    if (pidInfo.orchestratorPid) {
      await killProcessTree(pidInfo.orchestratorPid);
    }

    // Kill dashboard
    if (pidInfo.dashboardPid) {
      await killProcessTree(pidInfo.dashboardPid);
    }

    // 3. Clean up PID file
    await removePidFile(projectRoot);

    spinner.succeed("Pulse stopped");
    printSuccess("All processes have been shut down.");
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    spinner.fail(`Error stopping Pulse: ${message}`);

    // Clean up PID file anyway — processes might already be dead
    await removePidFile(projectRoot);
    printWarning("PID file cleaned up. Processes may have already stopped.");
  }

  console.log();
}
