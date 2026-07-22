"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, FileCode, Shield } from "lucide-react";
import { SeverityBadge } from "../shared/SeverityBadge";
import type { Finding } from "../../lib/socket";
import styles from "./FindingsPanel.module.css";

function FindingCard({ finding, index }: { finding: Finding; index: number }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={styles.card}
    >
      <button
        className={styles.cardHeader}
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
      >
        <div className={styles.cardTitle}>
          <SeverityBadge severity={finding.severity} />
          <span className={styles.findingTitle}>{finding.title}</span>
        </div>
        <ChevronDown
          size={14}
          className={`${styles.chevron} ${isExpanded ? styles.chevronOpen : ""}`}
        />
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className={styles.cardBody}
          >
            <div className={styles.fileMeta}>
              <FileCode size={12} />
              <span className={styles.filePath}>{finding.file}</span>
              <span className={styles.lineNumber}>L{finding.line}</span>
            </div>

            <p className={styles.explanation}>{finding.explanation}</p>

            {finding.suggested_fix && (
              <div className={styles.fixBlock}>
                <span className={styles.fixLabel}>SUGGESTED FIX</span>
                <pre className={styles.fixCode}>
                  <code>{finding.suggested_fix}</code>
                </pre>
              </div>
            )}

            {finding.confidence != null && (
              <div className={styles.confidence}>
                <span className={styles.confidenceLabel}>CONFIDENCE</span>
                <div className={styles.confidenceBar}>
                  <div
                    className={styles.confidenceFill}
                    style={{ width: `${finding.confidence * 100}%` }}
                  />
                </div>
                <span className={styles.confidenceValue}>
                  {Math.round(finding.confidence * 100)}%
                </span>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function FindingsPanel({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return (
      <div className={styles.container}>
        <div className={styles.label}>
          <span className={styles.labelText}>FINDINGS</span>
        </div>
        <div className={styles.empty}>
          <Shield size={24} className={styles.emptyIcon} />
          <span className={styles.emptyLabel}>NO FINDINGS YET</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.label}>
        <span className={styles.labelText}>
          FINDINGS · {findings.length}
        </span>
      </div>
      <div className={styles.list}>
        {findings.map((finding, i) => (
          <FindingCard key={`${finding.file}-${finding.line}-${i}`} finding={finding} index={i} />
        ))}
      </div>
    </div>
  );
}
