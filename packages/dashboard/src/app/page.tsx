"use client";

import { useState, useCallback } from "react";
import {
  Network,
  BarChart3,
  ScrollText,
  ShieldAlert,
} from "lucide-react";
import { CommandBar } from "../components/CommandBar/CommandBar";
import { NeuralGraph } from "../components/NeuralGraph/NeuralGraph";
import { Timeline } from "../components/Timeline/Timeline";
import { MetricsPanel } from "../components/Metrics/MetricsPanel";
import { FindingsPanel } from "../components/Findings/FindingsPanel";
import { Scanline } from "../components/shared/Scanline";
import { usePulseSocket } from "../lib/socket";
import styles from "./page.module.css";

type Section = "network" | "metrics" | "timeline" | "findings";

const NAV_ITEMS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: "network", label: "NETWORK", icon: <Network size={22} /> },
  { id: "timeline", label: "LOG", icon: <ScrollText size={22} /> },
  { id: "metrics", label: "METRICS", icon: <BarChart3 size={22} /> },
  { id: "findings", label: "FINDINGS", icon: <ShieldAlert size={22} /> },
];

export default function Dashboard() {
  const [activeSection, setActiveSection] = useState<Section>("network");

  const {
    isConnected,
    events,
    agentStates,
    currentReview,
    latestFindings,
    metrics,
  } = usePulseSocket();

  const handleSimulate = useCallback(async () => {
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
  }, []);

  const handleKeyNav = (e: React.KeyboardEvent, section: Section) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setActiveSection(section);
    }
  };

  return (
    <div className={styles.root}>
      <Scanline />
      <CommandBar isConnected={isConnected} onSimulate={handleSimulate} />

      <div className={styles.shell}>
        {/* ─── Workspace ─── */}
        <main className={styles.workspace}>
          {activeSection === "network" && (
            <NeuralGraph
              agentStates={agentStates}
              isReviewActive={currentReview?.isActive ?? false}
            />
          )}

          {activeSection === "timeline" && <Timeline events={events} />}

          {activeSection === "metrics" && (
            <MetricsPanel
              totalReviews={metrics.totalReviews}
              totalFindings={metrics.totalFindings}
              criticalCount={metrics.criticalCount}
              totalTokens={metrics.totalTokens}
            />
          )}

          {activeSection === "findings" && (
            <FindingsPanel findings={latestFindings} />
          )}
        </main>

        {/* ─── Right Sidebar Nav ─── */}
        <nav className={styles.nav} aria-label="Dashboard sections">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`${styles.navItem} ${activeSection === item.id ? styles.navItemActive : ""}`}
              onClick={() => setActiveSection(item.id)}
              onKeyDown={(e) => handleKeyNav(e, item.id)}
              title={item.label}
              aria-current={activeSection === item.id ? "page" : undefined}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              <span className={styles.navLabel}>{item.label}</span>
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
