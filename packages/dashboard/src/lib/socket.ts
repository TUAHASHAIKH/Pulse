"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { io, Socket } from "socket.io-client";
import type { AgentStatus } from "./agents";

/* ─── Types ─── */

export type Severity = "critical" | "warning" | "info";

export interface Finding {
  file: string;
  line: number;
  severity: Severity;
  category: string;
  title: string;
  explanation: string;
  suggested_fix?: string;
  confidence?: number;
}

export interface AgentResult {
  agent_name: string;
  findings: Finding[];
  summary: string;
  token_usage: {
    input_tokens: number;
    output_tokens: number;
    model: string;
  };
  duration_seconds: number;
  error?: string;
}

export interface PulseEvent {
  id: string;
  timestamp: number;
  type:
    | "webhook_received"
    | "review_started"
    | "agent_started"
    | "agent_completed"
    | "review_completed";
  payload: Record<string, any>;
}

/** Derived state for an agent's current status in the graph. */
export interface AgentRuntimeState {
  agentId: string;
  status: AgentStatus;
  startedAt?: number;
  completedAt?: number;
  duration?: number;
  findingsCount?: number;
  error?: string;
  summary?: string;
}

/** Derived state for the current review session. */
export interface ReviewSession {
  reviewId: string;
  source: string;
  startedAt: number;
  completedAt?: number;
  totalFindings?: number;
  results?: AgentResult[];
  isActive: boolean;
}

/* ─── Constants ─── */

const ORCHESTRATOR_URL = "http://localhost:8000";

/* ─── Hook ─── */

export function usePulseSocket() {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<PulseEvent[]>([]);

  useEffect(() => {
    const socketInstance = io(ORCHESTRATOR_URL, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
    });

    socketInstance.on("connect", () => {
      setIsConnected(true);
      console.log("[Pulse] Connected to Orchestrator");
    });

    socketInstance.on("disconnect", () => {
      setIsConnected(false);
      console.log("[Pulse] Disconnected from Orchestrator");
    });

    const addEvent = (type: PulseEvent["type"], payload: Record<string, any>) => {
      setEvents((prev) => [
        {
          id: `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          timestamp: Date.now(),
          type,
          payload,
        },
        ...prev,
      ]);
    };

    socketInstance.on("webhook_received", (data) => addEvent("webhook_received", data));
    socketInstance.on("review_started", (data) => addEvent("review_started", data));
    socketInstance.on("agent_started", (data) => addEvent("agent_started", data));
    socketInstance.on("agent_completed", (data) => addEvent("agent_completed", data));
    socketInstance.on("review_completed", (data) => addEvent("review_completed", data));

    setSocket(socketInstance);

    return () => {
      socketInstance.disconnect();
    };
  }, []);

  const clearEvents = useCallback(() => setEvents([]), []);

  /* ─── Derived: Agent States ─── */
  const agentStates = useMemo((): Map<string, AgentRuntimeState> => {
    const states = new Map<string, AgentRuntimeState>();

    // Walk events in chronological order (oldest first)
    const chronological = [...events].reverse();

    for (const event of chronological) {
      if (event.type === "agent_started") {
        const agentId = event.payload.agent;
        states.set(agentId, {
          agentId,
          status: "running",
          startedAt: event.timestamp,
        });
      }

      if (event.type === "agent_completed") {
        const agentId = event.payload.agent;
        const existing = states.get(agentId);
        states.set(agentId, {
          agentId,
          status: event.payload.status === "error" ? "error" : "completed",
          startedAt: existing?.startedAt,
          completedAt: event.timestamp,
          duration: event.payload.duration,
          findingsCount: event.payload.findings_count,
          error: event.payload.error,
          summary: event.payload.summary,
        });
      }
    }

    return states;
  }, [events]);

  /* ─── Derived: Current Review Session ─── */
  const currentReview = useMemo((): ReviewSession | null => {
    const reviewStarted = events.find((e) => e.type === "review_started");
    if (!reviewStarted) return null;

    const reviewCompleted = events.find(
      (e) =>
        e.type === "review_completed" &&
        e.payload.review_id === reviewStarted.payload.review_id
    );

    return {
      reviewId: reviewStarted.payload.review_id,
      source: reviewStarted.payload.source,
      startedAt: reviewStarted.timestamp,
      completedAt: reviewCompleted?.timestamp,
      totalFindings: reviewCompleted?.payload.total_findings,
      results: reviewCompleted?.payload.results,
      isActive: !reviewCompleted,
    };
  }, [events]);

  /* ─── Derived: Latest Findings ─── */
  const latestFindings = useMemo((): Finding[] => {
    const completedReview = events.find((e) => e.type === "review_completed");
    if (!completedReview?.payload.results) return [];

    return completedReview.payload.results.flatMap(
      (r: AgentResult) => r.findings || []
    );
  }, [events]);

  /* ─── Derived: Aggregate Metrics ─── */
  const metrics = useMemo(() => {
    const reviewStarts = events.filter((e) => e.type === "review_started").length;
    const reviewCompletions = events.filter((e) => e.type === "review_completed");
    const totalFindings = reviewCompletions.reduce(
      (acc, e) => acc + (e.payload.total_findings || 0),
      0
    );
    const totalTokens = reviewCompletions.reduce((acc, e) => {
      const results: AgentResult[] = e.payload.results || [];
      return (
        acc +
        results.reduce(
          (a, r) =>
            a + (r.token_usage?.input_tokens || 0) + (r.token_usage?.output_tokens || 0),
          0
        )
      );
    }, 0);

    const criticalCount = reviewCompletions.reduce((acc, e) => {
      const results: AgentResult[] = e.payload.results || [];
      return (
        acc +
        results.reduce(
          (a, r) => a + (r.findings?.filter((f) => f.severity === "critical").length || 0),
          0
        )
      );
    }, 0);

    return {
      totalReviews: reviewStarts,
      totalFindings,
      totalTokens,
      criticalCount,
    };
  }, [events]);

  return {
    socket,
    isConnected,
    events,
    clearEvents,
    agentStates,
    currentReview,
    latestFindings,
    metrics,
  };
}
