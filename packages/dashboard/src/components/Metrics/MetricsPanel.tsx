"use client";

import { AnimatedCounter } from "../shared/AnimatedCounter";
import styles from "./MetricsPanel.module.css";

interface AgentTokenData {
  input: number;
  output: number;
  model: string;
  duration: number;
  findings: number;
}

interface MetricsPanelProps {
  metrics: {
    totalReviews: number;
    totalFindings: number;
    totalTokens: number;
    inputTokens: number;
    outputTokens: number;
    criticalCount: number;
    warningCount: number;
    repairsSucceeded: number;
    repairsFailed: number;
    agentTokens: Record<string, AgentTokenData>;
    totalDuration: number;
  };
}

/** Compact stat card with accent bar */
function StatCard({
  label,
  value,
  subLabel,
  color,
  suffix = "",
}: {
  label: string;
  value: number;
  subLabel?: string;
  color: string;
  suffix?: string;
}) {
  return (
    <div className={styles.statCard}>
      <span className={styles.statLabel}>{label}</span>
      <div className={styles.statValueRow}>
        <AnimatedCounter
          value={value}
          className={styles.statValue}
          suffix={suffix}
        />
      </div>
      {subLabel && <span className={styles.statSub}>{subLabel}</span>}
      <div
        className={styles.statBar}
        style={{
          background: color,
          boxShadow: value > 0 ? `0 0 8px ${color}` : "none",
          opacity: value > 0 ? 1 : 0.2,
        }}
      />
    </div>
  );
}

/** Agent token row for the breakdown table */
function AgentRow({
  name,
  data,
  totalTokens,
  color,
}: {
  name: string;
  data: AgentTokenData;
  totalTokens: number;
  color: string;
}) {
  const total = data.input + data.output;
  const pct = totalTokens > 0 ? Math.round((total / totalTokens) * 100) : 0;

  return (
    <div className={styles.agentRow}>
      <div className={styles.agentInfo}>
        <div className={styles.agentDot} style={{ background: color }} />
        <span className={styles.agentName}>{name}</span>
        {data.model && (
          <span className={styles.agentModel}>{data.model}</span>
        )}
      </div>
      <div className={styles.agentStats}>
        <span className={styles.agentTokenSplit}>
          <span style={{ color: "#00F0FF" }}>{data.input.toLocaleString()}</span>
          {" / "}
          <span style={{ color: "#B026FF" }}>{data.output.toLocaleString()}</span>
        </span>
        <span className={styles.agentFindings}>
          {data.findings} finding{data.findings !== 1 ? "s" : ""}
        </span>
        <span className={styles.agentDuration}>
          {data.duration.toFixed(1)}s
        </span>
      </div>
      <div className={styles.agentBarTrack}>
        <div
          className={styles.agentBarFill}
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

const AGENT_COLORS: Record<string, string> = {
  security_agent: "#FF2A6D",
  performance_agent: "#FFB800",
  code_quality_agent: "#00FF66",
  architect_agent: "#B026FF",
};

function getAgentColor(name: string): string {
  return AGENT_COLORS[name] || "#00F0FF";
}

function formatAgentName(name: string): string {
  return name
    .replace(/_agent$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function MetricsPanel({ metrics }: MetricsPanelProps) {
  const {
    totalReviews,
    totalFindings,
    totalTokens,
    inputTokens,
    outputTokens,
    criticalCount,
    warningCount,
    repairsSucceeded,
    repairsFailed,
    agentTokens,
    totalDuration,
  } = metrics;

  const isActive = totalReviews > 0;
  const infoCount = totalFindings - criticalCount - warningCount;
  const agentEntries = Object.entries(agentTokens);

  // Detect model from any agent
  const detectedModel =
    agentEntries.length > 0
      ? agentEntries[0][1].model || "—"
      : "—";

  return (
    <div className={styles.container}>
      {/* ─── Header ─── */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.title}>Review Metrics</span>
          <span className={styles.subtitle}>
            {isActive
              ? `${totalReviews} review${totalReviews !== 1 ? "s" : ""} completed`
              : "No reviews yet — run a review to see metrics"}
          </span>
        </div>
        <div className={styles.liveBadge}>
          <div
            className={styles.liveDot}
            style={{
              background: isActive ? "var(--nx-emerald)" : "var(--nx-text-ghost)",
              boxShadow: isActive ? "0 0 8px var(--nx-emerald)" : "none",
            }}
          />
          <span>{isActive ? "DATA AVAILABLE" : "STANDBY"}</span>
        </div>
      </div>

      {/* ─── Row 1: Key Stats (6 cards) ─── */}
      <div className={styles.statsGrid}>
        <StatCard
          label="REVIEWS"
          value={totalReviews}
          subLabel="Total runs"
          color="#00F0FF"
        />
        <StatCard
          label="FINDINGS"
          value={totalFindings}
          subLabel={`${criticalCount} critical · ${warningCount} warning · ${infoCount} info`}
          color="#B026FF"
        />
        <StatCard
          label="CRITICAL"
          value={criticalCount}
          subLabel={criticalCount > 0 ? "Action required" : "None detected"}
          color="#FF2A6D"
        />
        <StatCard
          label="REPAIRS"
          value={repairsSucceeded}
          subLabel={
            repairsFailed > 0
              ? `${repairsFailed} failed`
              : repairsSucceeded > 0
              ? "All succeeded"
              : "No repairs run"
          }
          color="#00FF66"
        />
        <StatCard
          label="DURATION"
          value={Number(totalDuration.toFixed(1))}
          suffix="s"
          subLabel="Total agent time"
          color="#FFB800"
        />
        <StatCard
          label="MODEL"
          value={totalTokens}
          subLabel={detectedModel}
          color="#00F0FF"
        />
      </div>

      {/* ─── Row 2: Token Breakdown ─── */}
      <div className={styles.splitGrid}>
        {/* Left: Input vs Output tokens */}
        <div className={styles.panelCard}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Token Consumption</span>
          </div>

          <div className={styles.tokenSummary}>
            <div className={styles.tokenBlock}>
              <span className={styles.tokenLabel}>INPUT TOKENS</span>
              <span className={styles.tokenValue} style={{ color: "#00F0FF" }}>
                <AnimatedCounter value={inputTokens} />
              </span>
              <span className={styles.tokenHint}>Prompts sent to LLM</span>
            </div>
            <div className={styles.tokenDivider} />
            <div className={styles.tokenBlock}>
              <span className={styles.tokenLabel}>OUTPUT TOKENS</span>
              <span className={styles.tokenValue} style={{ color: "#B026FF" }}>
                <AnimatedCounter value={outputTokens} />
              </span>
              <span className={styles.tokenHint}>Responses from LLM</span>
            </div>
            <div className={styles.tokenDivider} />
            <div className={styles.tokenBlock}>
              <span className={styles.tokenLabel}>TOTAL</span>
              <span className={styles.tokenValue} style={{ color: "var(--nx-text)" }}>
                <AnimatedCounter value={totalTokens} />
              </span>
              <span className={styles.tokenHint}>
                {totalTokens > 0
                  ? `Ratio: ${((inputTokens / totalTokens) * 100).toFixed(0)}% in / ${((outputTokens / totalTokens) * 100).toFixed(0)}% out`
                  : "—"}
              </span>
            </div>
          </div>

          {/* Token ratio bar */}
          {totalTokens > 0 && (
            <div className={styles.ratioBarTrack}>
              <div
                className={styles.ratioBarInput}
                style={{
                  width: `${(inputTokens / totalTokens) * 100}%`,
                }}
              />
              <div
                className={styles.ratioBarOutput}
                style={{
                  width: `${(outputTokens / totalTokens) * 100}%`,
                }}
              />
            </div>
          )}
        </div>

        {/* Right: Severity breakdown */}
        <div className={styles.panelCard}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Severity Breakdown</span>
          </div>

          <div className={styles.severityGrid}>
            <div className={styles.severityItem}>
              <div
                className={styles.severityDot}
                style={{ background: "#FF2A6D", boxShadow: "0 0 6px #FF2A6D" }}
              />
              <div className={styles.severityInfo}>
                <span className={styles.severityCount}>{criticalCount}</span>
                <span className={styles.severityLabel}>Critical</span>
              </div>
              {totalFindings > 0 && (
                <span className={styles.severityPct}>
                  {Math.round((criticalCount / totalFindings) * 100)}%
                </span>
              )}
            </div>

            <div className={styles.severityItem}>
              <div
                className={styles.severityDot}
                style={{ background: "#FFB800", boxShadow: "0 0 6px #FFB800" }}
              />
              <div className={styles.severityInfo}>
                <span className={styles.severityCount}>{warningCount}</span>
                <span className={styles.severityLabel}>Warning</span>
              </div>
              {totalFindings > 0 && (
                <span className={styles.severityPct}>
                  {Math.round((warningCount / totalFindings) * 100)}%
                </span>
              )}
            </div>

            <div className={styles.severityItem}>
              <div
                className={styles.severityDot}
                style={{ background: "#3b82f6", boxShadow: "0 0 6px #3b82f6" }}
              />
              <div className={styles.severityInfo}>
                <span className={styles.severityCount}>{infoCount}</span>
                <span className={styles.severityLabel}>Info</span>
              </div>
              {totalFindings > 0 && (
                <span className={styles.severityPct}>
                  {Math.round((infoCount / totalFindings) * 100)}%
                </span>
              )}
            </div>
          </div>

          {/* Severity stacked bar */}
          {totalFindings > 0 && (
            <div className={styles.ratioBarTrack}>
              <div
                style={{
                  width: `${(criticalCount / totalFindings) * 100}%`,
                  background: "#FF2A6D",
                  height: "100%",
                  borderRadius: "3px 0 0 3px",
                }}
              />
              <div
                style={{
                  width: `${(warningCount / totalFindings) * 100}%`,
                  background: "#FFB800",
                  height: "100%",
                }}
              />
              <div
                style={{
                  width: `${(infoCount / totalFindings) * 100}%`,
                  background: "#3b82f6",
                  height: "100%",
                  borderRadius: "0 3px 3px 0",
                }}
              />
            </div>
          )}
        </div>
      </div>

      {/* ─── Row 3: Per-Agent Breakdown ─── */}
      {agentEntries.length > 0 && (
        <div className={styles.panelCard}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Per-Agent Breakdown</span>
            <div className={styles.tokenLegend}>
              <span style={{ color: "#00F0FF", fontSize: "11px" }}>● Input</span>
              <span style={{ color: "#B026FF", fontSize: "11px" }}>● Output</span>
            </div>
          </div>
          <div className={styles.agentList}>
            {agentEntries.map(([name, data]) => (
              <AgentRow
                key={name}
                name={formatAgentName(name)}
                data={data}
                totalTokens={totalTokens}
                color={getAgentColor(name)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
