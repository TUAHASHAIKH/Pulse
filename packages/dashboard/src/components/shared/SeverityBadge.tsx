"use client";

import type { Severity } from "@/lib/socket";
import styles from "./shared.module.css";

const SEVERITY_MAP: Record<
  Severity,
  { label: string; className: string }
> = {
  critical: { label: "CRITICAL", className: styles.severityCritical },
  warning: { label: "WARNING", className: styles.severityWarning },
  info: { label: "INFO", className: styles.severityInfo },
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const config = SEVERITY_MAP[severity];
  return (
    <span className={`${styles.severityBadge} ${config.className}`}>
      {config.label}
    </span>
  );
}
