"use client";

import { useState, useEffect } from "react";
import styles from "./SettingsPanel.module.css";

const ORCHESTRATOR_URL = "http://localhost:8000";

interface Settings {
  fix_delivery: "ask" | "local" | "pr_comment" | "branch";
  auto_repair: boolean;
  repair_max_attempts: number;
  auto_review_push: boolean;
  block_push: boolean;
  min_confidence_threshold: number;
  repair_min_confidence: number;
  max_findings_per_agent: number;
  strict_evidence_validation: boolean;
}

const DEFAULTS: Settings = {
  fix_delivery: "ask",
  auto_repair: true,
  repair_max_attempts: 3,
  auto_review_push: false,
  block_push: true,
  min_confidence_threshold: 0.6,
  repair_min_confidence: 0.7,
  max_findings_per_agent: 5,
  strict_evidence_validation: true,
};

export function SettingsPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  useEffect(() => {
    fetch(`${ORCHESTRATOR_URL}/api/settings`)
      .then((res) => res.json())
      .then((data) => {
        // Merge with defaults so new keys are always present
        setSettings({ ...DEFAULTS, ...data });
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load settings:", err);
        setLoading(false);
      });
  }, []);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setFeedback(null);

    try {
      const res = await fetch(`${ORCHESTRATOR_URL}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      const data = await res.json();
      if (data.success) {
        setFeedback({ type: "success", message: "Settings saved" });
        setTimeout(() => setFeedback(null), 3000);
      } else {
        setFeedback({ type: "error", message: "Failed to save" });
      }
    } catch (err) {
      setFeedback({ type: "error", message: `Error: ${err}` });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className={styles.container}>Loading settings...</div>;
  }

  if (!settings) {
    return <div className={styles.container}>Failed to load settings.</div>;
  }

  return (
    <div className={styles.container}>
      {/* ─── Header ─── */}
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <div className={styles.titleIcon}>⚙</div>
          <h2 className={styles.title}>Settings</h2>
        </div>
        <p className={styles.subtitle}>
          Configure how Pulse reviews, repairs, and delivers fixes
        </p>
      </div>

      {/* ═══════════════════════════════════════════
          SECTION 1: Git Push Integration
          ═══════════════════════════════════════════ */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconGit}`}>
            ⎇
          </div>
          <h3 className={styles.sectionTitle}>Git Push Integration</h3>
        </div>
        <p className={styles.sectionDesc}>
          Automatically review code before every git push using a pre-push hook
        </p>

        {/* Auto Review on Push */}
        <div className={styles.toggleRow}>
          <div className={styles.toggleInfo}>
            <span className={styles.toggleLabel}>
              Auto-review before push
            </span>
            <span className={styles.toggleHint}>
              Runs Pulse review automatically when you run git push
            </span>
          </div>
          <button
            className={`${styles.toggleSwitch} ${
              settings.auto_review_push ? styles.toggleSwitchActive : ""
            }`}
            onClick={() =>
              setSettings({
                ...settings,
                auto_review_push: !settings.auto_review_push,
              })
            }
          >
            <div
              className={`${styles.toggleDot} ${
                settings.auto_review_push ? styles.toggleDotActive : ""
              }`}
            />
          </button>
        </div>

        {/* Block Push on Findings */}
        <div className={styles.toggleRow}>
          <div className={styles.toggleInfo}>
            <span className={styles.toggleLabel}>
              Block push when issues found
            </span>
            <span className={styles.toggleHint}>
              Prompts &quot;Continue pushing?&quot; when findings are detected.
              When off, push continues automatically
            </span>
          </div>
          <button
            className={`${styles.toggleSwitch} ${
              settings.block_push ? styles.toggleSwitchActive : ""
            }`}
            onClick={() =>
              setSettings({
                ...settings,
                block_push: !settings.block_push,
              })
            }
          >
            <div
              className={`${styles.toggleDot} ${
                settings.block_push ? styles.toggleDotActive : ""
              }`}
            />
          </button>
        </div>
      </div>

      {/* ═══════════════════════════════════════════
          SECTION 2: Repair Behavior
          ═══════════════════════════════════════════ */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconRepair}`}>
            🔧
          </div>
          <h3 className={styles.sectionTitle}>Repair Agent</h3>
        </div>
        <p className={styles.sectionDesc}>
          Configure how the Repair Agent generates and attempts fixes
        </p>

        {/* Auto Repair */}
        <div className={styles.toggleRow}>
          <div className={styles.toggleInfo}>
            <span className={styles.toggleLabel}>
              Auto-repair critical findings
            </span>
            <span className={styles.toggleHint}>
              Automatically generates fixes for critical and warning-level
              issues
            </span>
          </div>
          <button
            className={`${styles.toggleSwitch} ${
              settings.auto_repair ? styles.toggleSwitchActive : ""
            }`}
            onClick={() =>
              setSettings({
                ...settings,
                auto_repair: !settings.auto_repair,
              })
            }
          >
            <div
              className={`${styles.toggleDot} ${
                settings.auto_repair ? styles.toggleDotActive : ""
              }`}
            />
          </button>
        </div>

        {/* Max Attempts */}
        <div className={styles.numberRow}>
          <div className={styles.numberInfo}>
            <span className={styles.numberLabel}>Max repair attempts</span>
            <span className={styles.numberHint}>
              How many times the agent retries before giving up (1–5)
            </span>
          </div>
          <input
            type="number"
            min="1"
            max="5"
            value={settings.repair_max_attempts}
            onChange={(e) =>
              setSettings({
                ...settings,
                repair_max_attempts: parseInt(e.target.value) || 3,
              })
            }
            className={styles.numberInput}
          />
        </div>
      </div>

      {/* ═══════════════════════════════════════════
          SECTION 3: Fix Delivery
          ═══════════════════════════════════════════ */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <div
            className={`${styles.sectionIcon} ${styles.sectionIconDelivery}`}
          >
            📦
          </div>
          <h3 className={styles.sectionTitle}>Fix Delivery</h3>
        </div>
        <p className={styles.sectionDesc}>
          How should verified fixes be delivered to your codebase?
        </p>

        <div className={styles.radioGroup}>
          {[
            {
              id: "ask",
              label: "Ask every time",
              hint: "Show apply/comment/branch buttons in the dashboard",
            },
            {
              id: "local",
              label: "Always apply locally",
              hint: "Applies the patch directly to your working tree via git apply",
            },
            {
              id: "pr_comment",
              label: "Post as PR comment",
              hint: "Posts the fix as a suggestion comment on the pull request",
            },
            {
              id: "branch",
              label: "Commit to new branch",
              hint: "Creates a pulse/fix-* branch with the fix committed",
            },
          ].map((option) => (
            <label
              key={option.id}
              className={`${styles.radioOption} ${
                settings.fix_delivery === option.id
                  ? styles.radioOptionSelected
                  : ""
              }`}
            >
              <input
                type="radio"
                name="fix_delivery"
                value={option.id}
                checked={settings.fix_delivery === option.id}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    fix_delivery: e.target.value as Settings["fix_delivery"],
                  })
                }
                className={styles.radioInput}
              />
              <div className={styles.radioInfo}>
                <span
                  className={`${styles.radioLabel} ${
                    settings.fix_delivery === option.id
                      ? styles.radioLabelSelected
                      : ""
                  }`}
                >
                  {option.label}
                </span>
                <span className={styles.radioHint}>{option.hint}</span>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* ═══════════════════════════════════════════
          SECTION 4: Review Quality
          ═══════════════════════════════════════════ */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconDelivery}`}>
            🎯
          </div>
          <h3 className={styles.sectionTitle}>Review Quality</h3>
        </div>
        <p className={styles.sectionDesc}>
          Thresholds that filter low-confidence findings and limit noise
        </p>

        <div className={styles.numberRow}>
          <div className={styles.numberInfo}>
            <span className={styles.numberLabel}>Min finding confidence</span>
            <span className={styles.numberHint}>Findings below this are dropped (0.0–1.0)</span>
          </div>
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={settings.min_confidence_threshold}
            onChange={(e) =>
              setSettings({
                ...settings,
                min_confidence_threshold: parseFloat(e.target.value) || 0.6,
              })
            }
            className={styles.numberInput}
          />
        </div>

        <div className={styles.numberRow}>
          <div className={styles.numberInfo}>
            <span className={styles.numberLabel}>Min repair confidence</span>
            <span className={styles.numberHint}>Only repair findings above this level</span>
          </div>
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={settings.repair_min_confidence}
            onChange={(e) =>
              setSettings({
                ...settings,
                repair_min_confidence: parseFloat(e.target.value) || 0.7,
              })
            }
            className={styles.numberInput}
          />
        </div>

        <div className={styles.numberRow}>
          <div className={styles.numberInfo}>
            <span className={styles.numberLabel}>Max findings per agent</span>
            <span className={styles.numberHint}>Caps findings to reduce noise (1–10)</span>
          </div>
          <input
            type="number"
            min="1"
            max="10"
            value={settings.max_findings_per_agent}
            onChange={(e) =>
              setSettings({
                ...settings,
                max_findings_per_agent: parseInt(e.target.value) || 5,
              })
            }
            className={styles.numberInput}
          />
        </div>

        <div className={styles.toggleRow}>
          <div className={styles.toggleInfo}>
            <span className={styles.toggleLabel}>Strict evidence validation</span>
            <span className={styles.toggleHint}>
              Reject findings whose evidence cannot be found in the diff
            </span>
          </div>
          <button
            className={`${styles.toggleSwitch} ${
              settings.strict_evidence_validation ? styles.toggleSwitchActive : ""
            }`}
            onClick={() =>
              setSettings({
                ...settings,
                strict_evidence_validation: !settings.strict_evidence_validation,
              })
            }
          >
            <div
              className={`${styles.toggleDot} ${
                settings.strict_evidence_validation ? styles.toggleDotActive : ""
              }`}
            />
          </button>
        </div>
      </div>

      {/* ─── Save Footer ─── */}
      <div className={styles.footer}>
        <button
          className={styles.saveBtn}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save Changes"}
        </button>

        {feedback && (
          <div
            className={`${styles.feedback} ${
              feedback.type === "success"
                ? styles.feedbackSuccess
                : styles.feedbackError
            }`}
          >
            {feedback.type === "success" ? "✓" : "✕"} {feedback.message}
          </div>
        )}
      </div>
    </div>
  );
}
