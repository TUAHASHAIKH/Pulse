"use client";

import { Activity, ShieldCheck, Terminal, AlertTriangle, Play, CheckCircle } from "lucide-react";
import type { PulseEvent } from "../lib/socket";
import styles from "./EventCard.module.css";

export function EventCard({ event }: { event: PulseEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString();

  switch (event.type) {
    case "webhook_received":
      return (
        <div className={`glass-panel ${styles.card} ${styles.webhook}`}>
          <div className={`${styles.iconContainer} ${styles.webhookIcon}`}>
            <Activity size={24} />
          </div>
          <div className={styles.content}>
            <div className={styles.header}>
              <h3 className={styles.title}>Webhook Received</h3>
              <span className={styles.time}>{time}</span>
            </div>
            <p className={styles.description}>
              <strong>{event.payload.author}</strong> opened PR #{event.payload.pr_number} in <strong>{event.payload.repo}</strong>
            </p>
          </div>
        </div>
      );

    case "review_started":
      return (
        <div className={`glass-panel ${styles.card} ${styles.review}`}>
          <div className={`${styles.iconContainer} ${styles.reviewIcon}`}>
            <Play size={24} />
          </div>
          <div className={styles.content}>
            <div className={styles.header}>
              <h3 className={styles.title}>Review Initiated</h3>
              <span className={styles.time}>{time}</span>
            </div>
            <p className={styles.description}>
              Orchestrator picked up {event.payload.source} review (ID: {event.payload.review_id})
            </p>
          </div>
        </div>
      );

    case "agent_started":
      return (
        <div className={`glass-panel ${styles.card} ${styles.agentStart}`}>
          <div className={`${styles.iconContainer} ${styles.agentStartIcon}`}>
            <Terminal size={24} />
          </div>
          <div className={styles.content}>
            <div className={styles.header}>
              <h3 className={styles.title}>{event.payload.agent} Agent Running</h3>
              <span className={styles.time}>{time}</span>
            </div>
            <p className={styles.description}>{event.payload.message}</p>
          </div>
        </div>
      );

    case "agent_completed":
      const isError = event.payload.status === "error";
      return (
        <div className={`glass-panel ${styles.card} ${isError ? styles.agentError : styles.agentSuccess}`}>
          <div className={`${styles.iconContainer} ${isError ? styles.agentErrorIcon : styles.agentSuccessIcon}`}>
            {isError ? <AlertTriangle size={24} /> : <ShieldCheck size={24} />}
          </div>
          <div className={styles.content}>
            <div className={styles.header}>
              <h3 className={styles.title}>
                {event.payload.agent} Agent {isError ? 'Failed' : 'Completed'}
              </h3>
              <span className={styles.time}>{time}</span>
            </div>
            <p className={styles.description}>
              {isError ? event.payload.error : event.payload.summary}
            </p>
            {!isError && (
              <div className={styles.metrics}>
                <span>⏱️ {event.payload.duration}s</span>
                <span>🐛 {event.payload.findings_count} findings</span>
              </div>
            )}
          </div>
        </div>
      );

    case "review_completed":
      return (
        <div className={`glass-panel ${styles.card} ${styles.webhook}`}>
          <div className={`${styles.iconContainer} ${styles.webhookIcon}`}>
            <CheckCircle size={24} />
          </div>
          <div className={styles.content}>
            <div className={styles.header}>
              <h3 className={styles.title}>Review Finished</h3>
              <span className={styles.time}>{time}</span>
            </div>
            <p className={styles.description}>
              Review {event.payload.review_id} complete. Found {event.payload.total_findings} total issues.
            </p>
          </div>
        </div>
      );

    default:
      return null;
  }
}
