"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  Play,
  Terminal,
  ShieldCheck,
  AlertTriangle,
  CheckCircle,
  Inbox,
} from "lucide-react";
import type { PulseEvent } from "../../lib/socket";
import { getAgentConfig } from "../../lib/agents";
import styles from "./Timeline.module.css";

const EVENT_CONFIG: Record<
  PulseEvent["type"],
  { icon: React.ReactNode; label: string; colorVar: string }
> = {
  webhook_received: {
    icon: <Activity size={14} />,
    label: "WEBHOOK",
    colorVar: "var(--nx-blue)",
  },
  review_started: {
    icon: <Play size={14} />,
    label: "REVIEW",
    colorVar: "var(--nx-purple)",
  },
  agent_started: {
    icon: <Terminal size={14} />,
    label: "AGENT",
    colorVar: "var(--nx-cyan)",
  },
  agent_completed: {
    icon: <ShieldCheck size={14} />,
    label: "RESULT",
    colorVar: "var(--nx-emerald)",
  },
  review_completed: {
    icon: <CheckCircle size={14} />,
    label: "COMPLETE",
    colorVar: "var(--nx-emerald)",
  },
};

function TimelineNode({ event }: { event: PulseEvent }) {
  const config = EVENT_CONFIG[event.type];
  const time = new Date(event.timestamp).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const isError =
    event.type === "agent_completed" && event.payload.status === "error";
  const agentConfig =
    event.payload.agent ? getAgentConfig(event.payload.agent) : null;

  const effectiveColor = isError ? "var(--nx-red)" : config.colorVar;

  const getDescription = (): string => {
    switch (event.type) {
      case "webhook_received":
        return `PR #${event.payload.pr_number} by ${event.payload.author}`;
      case "review_started":
        return `Review ${event.payload.review_id} · ${event.payload.source}`;
      case "agent_started":
        return event.payload.message || `${event.payload.agent} scanning...`;
      case "agent_completed":
        if (isError) return event.payload.error?.slice(0, 80) || "Failed";
        return `${event.payload.findings_count || 0} findings · ${event.payload.duration?.toFixed(1) || "0"}s`;
      case "review_completed":
        return `${event.payload.total_findings || 0} total findings`;
      default:
        return "";
    }
  };

  return (
    <div className={styles.node}>
      {/* Timeline dot */}
      <div className={styles.dotColumn}>
        <div
          className={`${styles.dot} ${isError ? styles.dotError : ""}`}
          style={{ "--node-color": effectiveColor } as React.CSSProperties}
        >
          {config.icon}
        </div>
        <div className={styles.line} />
      </div>

      {/* Content */}
      <div className={styles.content}>
        <div className={styles.nodeHeader}>
          <span
            className={styles.badge}
            style={{ "--node-color": effectiveColor } as React.CSSProperties}
          >
            {agentConfig ? agentConfig.shortName : config.label}
          </span>
          <span className={styles.timestamp}>{time}</span>
        </div>
        <p className={styles.description}>{getDescription()}</p>
        {event.type === "agent_completed" && !isError && event.payload.summary && (
          <p className={styles.summary}>{event.payload.summary}</p>
        )}
      </div>
    </div>
  );
}

export function Timeline({ events }: { events: PulseEvent[] }) {
  if (events.length === 0) {
    return (
      <div className={styles.empty}>
        <Inbox size={32} className={styles.emptyIcon} />
        <span className={styles.emptyLabel}>AWAITING SIGNAL</span>
        <p className={styles.emptyHint}>
          Click SIMULATE or open a PR to begin
        </p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.label}>
        <span className={styles.labelText}>EXECUTION LOG</span>
      </div>
      <div className={styles.feed}>
        <AnimatePresence initial={false}>
          {events.map((event) => (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 12 }}
              transition={{
                duration: 0.4,
                ease: [0.16, 1, 0.3, 1],
              }}
            >
              <TimelineNode event={event} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
