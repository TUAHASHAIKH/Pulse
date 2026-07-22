"use client";

import { useState } from "react";
import { Play, Zap, Terminal } from "lucide-react";
import { GlowDot } from "../shared/GlowDot";
import styles from "./CommandBar.module.css";

interface CommandBarProps {
  isConnected: boolean;
  onSimulate: () => Promise<void>;
}

export function CommandBar({ isConnected, onSimulate }: CommandBarProps) {
  const [isSimulating, setIsSimulating] = useState(false);

  const handleSimulate = async () => {
    setIsSimulating(true);
    try {
      await onSimulate();
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <header className={styles.bar}>
      {/* Logo */}
      <div className={styles.logoSection}>
        <div className={styles.logoIcon}>
          <Zap size={16} />
        </div>
        <span className={styles.logoText}>PULSE</span>
        <span className={styles.versionBadge}>v0.1</span>
      </div>

      {/* Center — Status */}
      <div className={styles.statusSection}>
        <div className={styles.statusIndicator}>
          <GlowDot
            color={isConnected ? "var(--nx-emerald)" : "var(--nx-red)"}
            mode={isConnected ? "pulse" : "flicker"}
            size={6}
          />
          <span className={styles.statusText}>
            {isConnected ? "ORCHESTRATOR ONLINE" : "DISCONNECTED"}
          </span>
        </div>
        <div className={styles.divider} />
        <div className={styles.statusMeta}>
          <Terminal size={12} className={styles.metaIcon} />
          <span className={styles.metaText}>localhost:8000</span>
        </div>
      </div>

      {/* Right — Actions */}
      <div className={styles.actionsSection}>
        <button
          className={styles.simulateButton}
          onClick={handleSimulate}
          disabled={!isConnected || isSimulating}
          title="Send a mock vulnerable PR to the orchestrator"
        >
          <Play size={12} />
          <span>{isSimulating ? "SCANNING..." : "SIMULATE"}</span>
        </button>
      </div>
    </header>
  );
}
