"use client";

import { useState, useEffect } from "react";
import styles from "./SettingsPanel.module.css";

const ORCHESTRATOR_URL = "http://localhost:8000";

interface Settings {
  fix_delivery: "ask" | "local" | "pr_comment" | "branch";
  auto_repair: boolean;
  repair_max_attempts: number;
}

export function SettingsPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${ORCHESTRATOR_URL}/api/settings`)
      .then((res) => res.json())
      .then((data) => {
        setSettings(data);
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
        setFeedback("✅ Settings saved successfully");
        setTimeout(() => setFeedback(null), 3000);
      } else {
        setFeedback("❌ Failed to save settings");
      }
    } catch (err) {
      setFeedback(`❌ Error: ${err}`);
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
      <h2 className={styles.title}>⚙️ Settings</h2>

      {/* Fix Delivery Section */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Fix Delivery</h3>
        <p className={styles.sectionDesc}>
          When the Repair Agent produces a verified fix, how should it be delivered?
        </p>

        <div className={styles.radioGroup}>
          {[
            { id: "ask", label: "Ask every time (show buttons in dashboard)" },
            { id: "local", label: "Always apply locally (git apply)" },
            { id: "pr_comment", label: "Always post as PR comment" },
            { id: "branch", label: "Always commit to a new branch" },
          ].map((option) => (
            <label
              key={option.id}
              className={`${styles.radioOption} ${
                settings.fix_delivery === option.id ? styles.radioOptionSelected : ""
              }`}
            >
              <input
                type="radio"
                name="fix_delivery"
                value={option.id}
                checked={settings.fix_delivery === option.id}
                onChange={(e) =>
                  setSettings({ ...settings, fix_delivery: e.target.value as any })
                }
                className={styles.radioInput}
              />
              <span
                className={`${styles.radioLabel} ${
                  settings.fix_delivery === option.id ? styles.radioLabelSelected : ""
                }`}
              >
                {option.label}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Repair Behavior Section */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Repair Behavior</h3>
        <p className={styles.sectionDesc}>
          Configure how the Repair Agent operates.
        </p>

        <label className={styles.toggle}>
          <span className={styles.toggleLabel}>Auto-repair critical findings</span>
          <button
            className={`${styles.toggleSwitch} ${
              settings.auto_repair ? styles.toggleSwitchActive : ""
            }`}
            onClick={() =>
              setSettings({ ...settings, auto_repair: !settings.auto_repair })
            }
          >
            <div
              className={`${styles.toggleDot} ${
                settings.auto_repair ? styles.toggleDotActive : ""
              }`}
            />
          </button>
        </label>

        <div className={styles.numberRow}>
          <span className={styles.numberLabel}>Max repair attempts per finding</span>
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

      <button
        className={styles.saveBtn}
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? "Saving..." : "Save Changes"}
      </button>

      {feedback && <div className={styles.feedback}>{feedback}</div>}
    </div>
  );
}
