"use client";

import { useState } from "react";
import { Header } from "../components/Header";
import { LiveFeed } from "../components/LiveFeed";
import { usePulseSocket } from "../lib/socket";
import styles from "./page.module.css";
import { Play } from "lucide-react";

export default function Dashboard() {
  const { isConnected, events } = usePulseSocket();
  const [isSimulating, setIsSimulating] = useState(false);

  // Calculate some simple metrics from the events
  const totalReviews = events.filter(e => e.type === "review_started").length;
  const issuesFound = events
    .filter(e => e.type === "review_completed")
    .reduce((acc, curr) => acc + (curr.payload.total_findings || 0), 0);

  const handleSimulateReview = async () => {
    setIsSimulating(true);
    try {
      const mockDiff = `
--- src/auth.py
+++ src/auth.py
@@ -10,3 +10,4 @@
 def login(user_email, password):
-    cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (user_email, password))
+    # simplified login query for performance
+    cursor.execute(f"SELECT * FROM users WHERE email = '{user_email}' AND password = '{password}'")
+    API_KEY = "sk-live-1234567890abcdef1234567890abcdef"
`;
      await fetch("http://localhost:8000/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ diff: mockDiff }),
      });
    } catch (err) {
      console.error("Failed to simulate review:", err);
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <>
      <Header isConnected={isConnected} />

      <div className={styles.container}>
        <aside className={styles.sidebar}>
          <h2 className={styles.sidebarTitle}>System Metrics</h2>

          <div className={styles.metricCard}>
            <div className={styles.metricTitle}>Reviews Initiated</div>
            <div className={styles.metricValue}>{totalReviews}</div>
          </div>

          <div className={styles.metricCard}>
            <div className={styles.metricTitle}>Issues Found</div>
            <div className={styles.metricValue} style={{ color: issuesFound > 0 ? 'var(--accent-warning)' : 'inherit' }}>
              {issuesFound}
            </div>
          </div>

          <div className={styles.actionSection}>
            <h3 className={styles.actionTitle}>Testing</h3>
            <button 
              className={styles.simulateButton} 
              onClick={handleSimulateReview}
              disabled={!isConnected || isSimulating}
            >
              <Play size={16} />
              {isSimulating ? "Sending..." : "Simulate Vulnerable PR"}
            </button>
            <p className={styles.actionHint}>
              Sends a mock SQL Injection diff to the Orchestrator to see the Security Agent in action.
            </p>
          </div>
        </aside>

        <main className={styles.main}>
          <LiveFeed events={events} />
        </main>
      </div>
    </>
  );
}
