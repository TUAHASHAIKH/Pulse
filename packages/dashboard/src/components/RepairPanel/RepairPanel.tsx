"use client";

import { useState, useCallback } from "react";
import { FolderOpen, MessageSquare, GitBranch } from "lucide-react";
import type { RepairResult } from "../../lib/socket";
import styles from "./RepairPanel.module.css";

const ORCHESTRATOR_URL = "http://localhost:8000";

interface RepairPanelProps {
  repairs: RepairResult[];
  reviewId: string;
  reviewSource?: string;
}

export function RepairPanel({ repairs, reviewId, reviewSource = "cli" }: RepairPanelProps) {
  if (repairs.length === 0) {
    return (
      <div className={styles.container}>
        <h2 className={styles.title}>🔧 Repair Agent</h2>
        <div className={styles.empty}>
          No repair results yet.
          <br />
          Critical findings trigger the Repair Agent automatically.
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <h2 className={styles.title}>🔧 Repair Agent</h2>
      {repairs.map((repair, i) => (
        <RepairCard
          key={`${repair.finding_index}-${i}`}
          repair={repair}
          reviewId={reviewId}
          reviewSource={reviewSource}
        />
      ))}
    </div>
  );
}

/* ─── Individual Repair Card ─── */

function RepairCard({
  repair,
  reviewId,
  reviewSource,
}: {
  repair: RepairResult;
  reviewId: string;
  reviewSource: string;
}) {
  const [showPatch, setShowPatch] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const applyFix = useCallback(
    async (method: "apply-local" | "pr-comment" | "commit-branch") => {
      setLoading(true);
      setFeedback(null);

      try {
        const res = await fetch(`${ORCHESTRATOR_URL}/api/fix/${method}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            review_id: reviewId,
            finding_index: repair.finding_index,
          }),
        });

        const data = await res.json();

        if (data.success) {
          setFeedback(`✅ ${data.message}`);
        } else {
          setFeedback(`❌ ${data.message}`);
        }
      } catch (err) {
        setFeedback(`❌ Failed to apply fix: ${err}`);
      } finally {
        setLoading(false);
      }
    },
    [reviewId, repair.finding_index]
  );

  const succeeded = repair.status === "succeeded";
  const unverified = repair.status === "unverified";
  const failed = repair.status === "failed";
  // Show delivery buttons whenever we have a patch (including unverified).
  // Previously docker-unavailable repairs were marked succeeded; unverified
  // should behave the same for manual fix delivery.
  const canApply = Boolean(repair.patch?.trim()) && !failed;

  return (
    <div className={styles.repairCard}>
      {/* Header */}
      <div className={styles.cardHeader}>
        <span className={styles.statusIcon}>
          {succeeded ? "✅" : unverified ? "⚠️" : failed ? "❌" : "⏳"}
        </span>
        <span className={styles.cardTitle}>{repair.finding_title}</span>
        <span
          className={`${styles.badge} ${
            succeeded ? styles.badgeSuccess : unverified ? styles.badgeWarning : styles.badgeFailed
          }`}
        >
          {succeeded
            ? "Fix Verified"
            : unverified
              ? "Unverified"
              : failed
                ? "Unfixable"
                : repair.status}
        </span>
      </div>

      {/* Meta info */}
      <div className={styles.meta}>
        <span>📁 {repair.finding_file}</span>
        <span>🎯 {(repair.confidence * 100).toFixed(0)}% confidence</span>
        <span>🔄 {repair.attempts_taken} attempt(s)</span>
        <span>⏱ {repair.duration_seconds.toFixed(1)}s</span>
      </div>

      {/* Explanation */}
      {repair.explanation && (
        <p className={styles.explanation}>{repair.explanation}</p>
      )}

      {/* Patch viewer */}
      {repair.patch && (
        <>
          <button
            className={styles.patchToggle}
            onClick={() => setShowPatch(!showPatch)}
          >
            {showPatch ? "▼ Hide Patch" : "▶ View Patch"}
          </button>

          {showPatch && (
            <div className={styles.patchBlock}>
              <pre>
                {repair.patch.split("\n").map((line, idx) => {
                  let className = styles.patchLine;
                  if (line.startsWith("+") && !line.startsWith("+++")) {
                    className = `${styles.patchLine} ${styles.patchAdded}`;
                  } else if (line.startsWith("-") && !line.startsWith("---")) {
                    className = `${styles.patchLine} ${styles.patchRemoved}`;
                  } else if (line.startsWith("@@")) {
                    className = `${styles.patchLine} ${styles.patchHeader}`;
                  }
                  return (
                    <span key={idx} className={className}>
                      {line}
                      {"\n"}
                    </span>
                  );
                })}
              </pre>
            </div>
          )}
        </>
      )}

      {/* Action Buttons — available for any repair with a patch */}
      {canApply && (
        <div className={styles.actions}>
          <button
            className={`${styles.actionBtn} ${styles.btnLocal}`}
            onClick={() => applyFix("apply-local")}
            disabled={loading}
            title="Apply changes to your local files (no commit)"
          >
            <FolderOpen size={14} />
            Apply Locally
          </button>
          <button
            className={`${styles.actionBtn} ${styles.btnComment}`}
            onClick={() => applyFix("pr-comment")}
            disabled={loading || reviewSource !== "webhook"}
            title={reviewSource !== "webhook" ? "PR Comment is only available for GitHub Webhook reviews." : "Post the fix as a comment on the GitHub PR"}
          >
            <MessageSquare size={14} />
            PR Comment
          </button>
          <button
            className={`${styles.actionBtn} ${styles.btnBranch}`}
            onClick={() => applyFix("commit-branch")}
            disabled={loading || reviewSource !== "webhook"}
            title={reviewSource !== "webhook" ? "Commit to Branch is only available for GitHub Webhook reviews." : "Commit the fix to a new pulse/fix branch"}
          >
            <GitBranch size={14} />
            Commit to Branch
          </button>
        </div>
      )}

      {/* Error message for failed repairs */}
      {failed && repair.error && (
        <p className={styles.explanation} style={{ color: "#ef4444" }}>
          {repair.error}
        </p>
      )}

      {/* Feedback after action */}
      {feedback && <div className={styles.actionFeedback}>{feedback}</div>}
    </div>
  );
}
