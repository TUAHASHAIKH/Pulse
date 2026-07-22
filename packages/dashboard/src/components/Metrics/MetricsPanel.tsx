"use client";

import { AnimatedCounter } from "../shared/AnimatedCounter";
import styles from "./MetricsPanel.module.css";

interface MetricsPanelProps {
  totalReviews: number;
  totalFindings: number;
  criticalCount: number;
  totalTokens: number;
}

/** SVG circular gauge component. */
function CircularGauge({
  value,
  maxValue,
  label,
  color,
  size = 80,
}: {
  value: number;
  maxValue: number;
  label: string;
  color: string;
  size?: number;
}) {
  const strokeWidth = 3;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = maxValue > 0 ? Math.min(value / maxValue, 1) : 0;
  const offset = circumference * (1 - progress);

  return (
    <div className={styles.gauge}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className={styles.gaugeSvg}
      >
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--nx-border)"
          strokeWidth={strokeWidth}
        />
        {/* Progress */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.16, 1, 0.3, 1)" }}
        />
      </svg>
      <div className={styles.gaugeContent}>
        <AnimatedCounter
          value={value}
          className={styles.gaugeValue}
        />
      </div>
      <span className={styles.gaugeLabel}>{label}</span>
    </div>
  );
}

/** Simple stat card for metrics that don't need a gauge. */
function StatCard({
  label,
  value,
  color,
  prefix = "",
  suffix = "",
}: {
  label: string;
  value: number;
  color: string;
  prefix?: string;
  suffix?: string;
}) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <AnimatedCounter
        value={value}
        className={styles.statValue}
        prefix={prefix}
        suffix={suffix}
      />
      <div
        className={styles.statBar}
        style={{ background: color, opacity: value > 0 ? 1 : 0.2 }}
      />
    </div>
  );
}

export function MetricsPanel({
  totalReviews,
  totalFindings,
  criticalCount,
  totalTokens,
}: MetricsPanelProps) {
  return (
    <div className={styles.container}>
      <div className={styles.label}>
        <span className={styles.labelText}>METRICS</span>
      </div>

      <div className={styles.gauges}>
        <CircularGauge
          value={totalReviews}
          maxValue={Math.max(totalReviews, 10)}
          label="REVIEWS"
          color="var(--nx-purple)"
        />
        <CircularGauge
          value={totalFindings}
          maxValue={Math.max(totalFindings, 10)}
          label="FINDINGS"
          color="var(--nx-cyan)"
        />
      </div>

      <div className={styles.stats}>
        <StatCard
          label="CRITICAL"
          value={criticalCount}
          color="var(--nx-red)"
        />
        <StatCard
          label="TOKENS"
          value={totalTokens}
          color="var(--nx-purple)"
        />
      </div>
    </div>
  );
}
