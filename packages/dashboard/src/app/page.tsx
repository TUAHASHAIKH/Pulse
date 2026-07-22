"use client";

import { CommandBar } from "../components/CommandBar/CommandBar";
import { NeuralGraph } from "../components/NeuralGraph/NeuralGraph";
import { Timeline } from "../components/Timeline/Timeline";
import { MetricsPanel } from "../components/Metrics/MetricsPanel";
import { FindingsPanel } from "../components/Findings/FindingsPanel";
import { Scanline } from "../components/shared/Scanline";
import { usePulseSocket } from "../lib/socket";
import styles from "./page.module.css";

export default function Dashboard() {
  const {
    isConnected,
    events,
    agentStates,
    currentReview,
    latestFindings,
    metrics,
  } = usePulseSocket();

  const handleSimulate = async () => {
    const mockDiff = `--- src/auth.py
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
  };

  return (
    <div className={styles.root}>
      <Scanline />
      <CommandBar isConnected={isConnected} onSimulate={handleSimulate} />

      <main className={styles.grid}>
        {/* Left column: Neural graph + Metrics */}
        <div className={styles.leftCol}>
          <div className={styles.graphPanel}>
            <NeuralGraph
              agentStates={agentStates}
              isReviewActive={currentReview?.isActive ?? false}
            />
          </div>
          <div className={styles.metricsPanel}>
            <MetricsPanel
              totalReviews={metrics.totalReviews}
              totalFindings={metrics.totalFindings}
              criticalCount={metrics.criticalCount}
              totalTokens={metrics.totalTokens}
            />
          </div>
        </div>

        {/* Right column: Timeline + Findings */}
        <div className={styles.rightCol}>
          <div className={styles.timelinePanel}>
            <Timeline events={events} />
          </div>
          <div className={styles.findingsPanel}>
            <FindingsPanel findings={latestFindings} />
          </div>
        </div>
      </main>
    </div>
  );
}
