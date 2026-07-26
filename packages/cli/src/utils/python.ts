/**
 * Pulse CLI — Python Environment Management
 *
 * Handles finding Python, creating venvs, and installing pip dependencies.
 * The orchestrator is a Python FastAPI app — the CLI manages its environment
 * so the user never has to touch pip or venv manually.
 */

import { execFile, exec } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { join } from "node:path";

const execFileAsync = promisify(execFile);
const execAsync = promisify(exec);

const MIN_PYTHON_VERSION = [3, 11];

// ─── Find Python ───

/**
 * Locate a Python 3.11+ binary on the system.
 * Tries `python3` first (Unix convention), then `python` (Windows).
 *
 * @returns Full path or command name of the Python binary
 * @throws Error with a helpful message if Python is not found or too old
 */
export async function findPython(): Promise<string> {
  const candidates = process.platform === "win32"
    ? ["python", "python3", "py -3"]
    : ["python3", "python"];

  for (const cmd of candidates) {
    try {
      const { stdout } = await execAsync(
        `${cmd} -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"`
      );

      const version = stdout.trim();
      const [major, minor] = version.split(".").map(Number);

      if (major >= MIN_PYTHON_VERSION[0] && minor >= MIN_PYTHON_VERSION[1]) {
        return cmd.includes(" ") ? cmd : cmd; // Return the command as-is
      }
    } catch {
      // This candidate doesn't exist or failed — try next
      continue;
    }
  }

  throw new Error(
    `Python ${MIN_PYTHON_VERSION.join(".")}+ is required but was not found.\n` +
    `  Install it from: https://www.python.org/downloads/\n` +
    `  Make sure it's in your PATH.`
  );
}

// ─── Venv Management ───

/**
 * Ensure a Python virtual environment exists at `.pulse/.venv/`.
 * Creates it if it doesn't exist.
 *
 * @param projectRoot - The project root directory (where .pulse/ lives)
 * @returns Path to the venv directory
 */
export async function ensureVenv(projectRoot: string): Promise<string> {
  const pulseDir = join(projectRoot, ".pulse");
  const venvPath = join(pulseDir, ".venv");

  if (existsSync(venvPath)) {
    return venvPath;
  }

  // Ensure .pulse/ directory exists
  await mkdir(pulseDir, { recursive: true });

  const pythonCmd = await findPython();
  await execAsync(`${pythonCmd} -m venv "${venvPath}"`);

  return venvPath;
}

/**
 * Get the platform-correct path to a binary inside the venv.
 * Windows uses Scripts/, Unix uses bin/.
 */
export function getVenvBin(venvPath: string, binary: string): string {
  const binDir = process.platform === "win32" ? "Scripts" : "bin";
  const ext = process.platform === "win32" ? ".exe" : "";
  return join(venvPath, binDir, binary + ext);
}

/**
 * Get the venv Python path.
 */
export function getVenvPython(venvPath: string): string {
  return getVenvBin(venvPath, "python");
}

// ─── Dependency Installation ───

/**
 * Install pip dependencies from requirements.txt, but only if
 * the requirements have changed since the last install.
 *
 * Uses a SHA-256 hash of requirements.txt stored in `.pulse/.deps-hash`
 * to skip redundant installs on subsequent runs.
 *
 * @param venvPath - Path to the venv directory
 * @param requirementsPath - Path to requirements.txt
 * @returns true if deps were installed, false if skipped
 */
export async function installDeps(
  venvPath: string,
  requirementsPath: string
): Promise<boolean> {
  const hashFile = join(venvPath, "..", ".deps-hash");

  // Hash the current requirements
  const reqContent = await readFile(requirementsPath, "utf-8");
  const currentHash = createHash("sha256").update(reqContent).digest("hex");

  // Check if we've already installed this exact set of deps
  if (existsSync(hashFile)) {
    try {
      const savedHash = await readFile(hashFile, "utf-8");
      if (savedHash.trim() === currentHash) {
        return false; // Already up to date
      }
    } catch {
      // Hash file is corrupt — reinstall
    }
  }

  // Install dependencies
  const pip = getVenvBin(venvPath, "pip");
  await execAsync(`"${pip}" install -r "${requirementsPath}"`, {
    maxBuffer: 1024 * 1024 * 10, // 10MB — pip can be verbose
  });

  // Save the hash for next time
  await writeFile(hashFile, currentHash, "utf-8");

  return true;
}
