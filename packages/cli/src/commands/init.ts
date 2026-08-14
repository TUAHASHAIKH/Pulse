/**
 * Pulse CLI — `pulse init`
 *
 * Interactive setup wizard that creates .pulse/config.json
 * with the user's API keys and preferences. Run once per project.
 */

import { existsSync } from "node:fs";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import { input, select, confirm, password } from "@inquirer/prompts";
import { printBanner, printSuccess, printWarning, printInfo, printError } from "../utils/ui.js";

// ─── Init Command ───

export async function initCommand(options: { force?: boolean }): Promise<void> {
  const projectRoot = process.cwd();
  const pulseDir = join(projectRoot, ".pulse");
  const configPath = join(pulseDir, "config.json");

  printBanner();

  // Check if config already exists
  if (existsSync(configPath) && !options.force) {
    const overwrite = await confirm({
      message: "Configuration already exists (.pulse/config.json). Overwrite?",
      default: false,
    });

    if (!overwrite) {
      printInfo("Keeping existing configuration.");
      return;
    }
  }

  console.log();
  printInfo("Let's set up Pulse for this project.\n");

  // 1. LLM Provider
  const llmProvider = await select({
    message: "Which LLM provider do you want to use?",
    choices: [
      { name: "Anthropic (Claude)", value: "anthropic" },
      { name: "OpenAI (GPT)", value: "openai" },
      { name: "Groq (fast inference)", value: "groq" },
    ],
    default: "anthropic",
  });

  // 2. LLM API Key
  const llmApiKey = await password({
    message: `Enter your ${llmProvider} API key:`,
    mask: "*",
    validate: (val) => {
      if (!val || val.trim().length === 0) {
        return "API key is required for Pulse to work.";
      }
      return true;
    },
  });

  // 3. GitHub Token (optional)
  const wantsGitHub = await confirm({
    message: "Do you want to set up GitHub integration? (for PR reviews & comments)",
    default: false,
  });

  let githubToken = "";
  if (wantsGitHub) {
    githubToken = await password({
      message: "Enter your GitHub Personal Access Token:",
      mask: "*",
    });
  }

  // 4. Auto-generate webhook secret
  const webhookSecret = randomBytes(32).toString("hex");

  // 5. Build config
  const config: Record<string, string> = {
    llm_provider: llmProvider,
    llm_api_key: llmApiKey,
    github_webhook_secret: webhookSecret,
  };

  if (githubToken) {
    config.github_token = githubToken;
  }

  // 6. Auto Push Review
  const wantsPushReview = await confirm({
    message: "Enable automatic code review before every git push?",
    default: false,
  });

  // 7. Write config
  await mkdir(pulseDir, { recursive: true });
  await writeFile(configPath, JSON.stringify(config, null, 2), "utf-8");

  // 8. Write settings (for push review toggle)
  if (wantsPushReview) {
    const settingsPath = join(pulseDir, "settings.json");
    const settings: Record<string, unknown> = {
      auto_review_push: true,
      block_push: true,
      auto_repair: true,
      fix_delivery: "ask",
      repair_max_attempts: 3,
    };
    await writeFile(settingsPath, JSON.stringify(settings, null, 2), "utf-8");
  }

  // 9. Ensure .pulse/ is in .gitignore
  await ensureGitignore(projectRoot);

  // 10. Install pre-push hook (if requested)
  if (wantsPushReview) {
    try {
      const { hooksCommand } = await import("./hooks.js");
      await hooksCommand("install");
    } catch {
      printWarning("Could not auto-install hook. Run `pulse hooks install` manually.");
    }
  }

  // 11. Success!
  console.log();
  printSuccess("Configuration saved to .pulse/config.json");
  console.log();
  printInfo("Next steps:");
  console.log("    1. Run:  pulse start");
  console.log("    2. Open: http://localhost:3000");

  if (wantsGitHub) {
    console.log();
    printInfo("GitHub Webhook Setup:");
    console.log("    1. Go to your repo → Settings → Webhooks → Add webhook");
    console.log("    2. Payload URL:   http://YOUR_SERVER:8000/webhook/github");
    console.log("    3. Content type:  application/json");
    console.log(`    4. Secret:        ${webhookSecret.slice(0, 8)}...`);
    console.log("    5. Events:        Pull requests");
  }

  if (wantsPushReview) {
    console.log();
    printSuccess("Auto push review enabled!");
    printInfo("Pulse will review your code before every git push.");
    printInfo("Disable anytime with: pulse hooks uninstall");
  }

  console.log();
}

// ─── Helpers ───

/**
 * Add `.pulse/` to .gitignore if it's not already there.
 */
async function ensureGitignore(projectRoot: string): Promise<void> {
  const gitignorePath = join(projectRoot, ".gitignore");

  if (!existsSync(gitignorePath)) {
    // No .gitignore — create one with just .pulse/
    await writeFile(gitignorePath, ".pulse/\n", "utf-8");
    printInfo("Created .gitignore with .pulse/ entry");
    return;
  }

  const content = await readFile(gitignorePath, "utf-8");

  if (content.includes(".pulse")) {
    // Already covered
    return;
  }

  // Append .pulse/ to the existing .gitignore
  const newContent = content.trimEnd() + "\n\n# Pulse local data\n.pulse/\n\n";
  await writeFile(gitignorePath, newContent, "utf-8");
  printInfo("Added .pulse/ to .gitignore");
}
