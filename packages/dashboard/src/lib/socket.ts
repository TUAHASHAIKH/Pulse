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

export interface RepairResult {
  finding_index: number;
  finding_title: string;
  finding_file: string;
  patch: string;
  explanation: string;
  test_output: string;
  tests_passed: boolean;
  attempts_taken: number;
  status: "pending" | "running" | "succeeded" | "failed";
  confidence: number;
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
    | "review_completed"
    | "repair_started"
    | "repair_attempt"
    | "repair_succeeded"
    | "repair_failed";
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
    socketInstance.on("repair_started", (data) => addEvent("repair_started", data));
    socketInstance.on("repair_attempt", (data) => addEvent("repair_attempt", data));
    socketInstance.on("repair_succeeded", (data) => addEvent("repair_succeeded", data));
    socketInstance.on("repair_failed", (data) => addEvent("repair_failed", data));

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
      if (event.type === "agent_started" || event.type === "repair_started") {
        const agentId =
          event.payload?.agent ||
          (event.type === "repair_started" ? "repair" : "");
        if (agentId) {
          states.set(agentId, {
            agentId,
            status: "running",
            startedAt: event.timestamp,
          });
        }
      }

      if (
        event.type === "agent_completed" ||
        event.type === "repair_succeeded" ||
        event.type === "repair_failed"
      ) {
        const agentId = event.payload?.agent || "repair";
        const existing = states.get(agentId);
        states.set(agentId, {
          agentId,
          status:
            event.type === "repair_failed" || event.payload?.status === "error"
              ? "error"
              : "completed",
          startedAt: existing?.startedAt,
          completedAt: event.timestamp,
          duration: event.payload?.duration || existing?.duration || 1.4,
          findingsCount: event.payload?.findings_count || 1,
          error: event.payload?.error,
          summary:
            event.payload?.summary ||
            event.payload?.explanation ||
            "Generated repair patch in sandbox",
        });
      }
    }

    return states;
  }, [events]);

  /* ─── Derived: Current Review Session ─── */
  const currentReview = useMemo((): ReviewSession | null => {
    const reviewStarted = events.find((e) => e.type === "review_started");
    if (!reviewStarted) return null;

    const reviewId = reviewStarted.payload.review_id;
    const allStarts = events.filter((e) => e.type === "review_started" && e.payload.review_id === reviewId);
    const allCompletions = events.filter((e) => e.type === "review_completed" && e.payload.review_id === reviewId);

    // It's active if we have more starts than completions (a batch is currently running)
    const isActive = allStarts.length > allCompletions.length;

    const totalFindings = allCompletions.reduce(
      (sum, e) => sum + (e.payload.total_findings || 0),
      0
    );

    return {
      reviewId,
      source: reviewStarted.payload.source,
      startedAt: allStarts[allStarts.length - 1].timestamp, // oldest start event
      completedAt: allCompletions.length > 0 ? allCompletions[0].timestamp : undefined, // newest completion
      totalFindings,
      results: allCompletions.flatMap((e) => e.payload.results || []),
      isActive,
    };
  }, [events]);

  /* ─── Derived: Current Review ID ─── */
  const currentReviewId = useMemo((): string => {
    const reviewStarted = events.find((e) => e.type === "review_started");
    return reviewStarted?.payload.review_id || "";
  }, [events]);

  /* ─── Derived: Latest Findings ─── */
  const latestFindings = useMemo((): Finding[] => {
    if (!currentReviewId) return [];

    const matchingEvents = events.filter(
      (e) => e.type === "review_completed" && e.payload.review_id === currentReviewId
    );

    return matchingEvents.flatMap((e) =>
      (e.payload.results || []).flatMap((r: AgentResult) => r.findings || [])
    );
  }, [events, currentReviewId]);

  /* ─── Derived: Aggregate Metrics ─── */
  const metrics = useMemo(() => {
    const reviewStarts = events.filter((e) => e.type === "review_started");
    const uniqueReviewIds = new Set(reviewStarts.map((e) => e.payload.review_id));
    const totalReviews = uniqueReviewIds.size;

    const reviewCompletions = events.filter((e) => e.type === "review_completed");
    const totalFindings = reviewCompletions.reduce(
      (acc, e) => acc + (e.payload.total_findings || 0),
      0
    );

    let inputTokens = 0;
    let outputTokens = 0;
    const agentTokens: Record<string, { input: number; output: number; model: string; duration: number; findings: number }> = {};

    for (const e of reviewCompletions) {
      const results: AgentResult[] = e.payload.results || [];
      for (const r of results) {
        const inT = r.token_usage?.input_tokens || 0;
        const outT = r.token_usage?.output_tokens || 0;
        inputTokens += inT;
        outputTokens += outT;

        const name = r.agent_name || "unknown";
        if (!agentTokens[name]) {
          agentTokens[name] = { input: 0, output: 0, model: r.token_usage?.model || "", duration: 0, findings: 0 };
        }
        agentTokens[name].input += inT;
        agentTokens[name].output += outT;
        agentTokens[name].duration += r.duration_seconds || 0;
        agentTokens[name].findings += r.findings?.length || 0;
        if (r.token_usage?.model) agentTokens[name].model = r.token_usage.model;
      }
    }

    const totalTokens = inputTokens + outputTokens;

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

    const warningCount = reviewCompletions.reduce((acc, e) => {
      const results: AgentResult[] = e.payload.results || [];
      return (
        acc +
        results.reduce(
          (a, r) => a + (r.findings?.filter((f) => f.severity === "warning").length || 0),
          0
        )
      );
    }, 0);

    // Real repair counts from events
    const repairsSucceeded = events.filter((e) => e.type === "repair_succeeded").length;
    const repairsFailed = events.filter((e) => e.type === "repair_failed").length;

    // Total review duration from actual events
    let totalDuration = 0;
    for (const e of reviewCompletions) {
      const results: AgentResult[] = e.payload.results || [];
      for (const r of results) {
        totalDuration += r.duration_seconds || 0;
      }
    }

    return {
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
    };
  }, [events]);

  /* ─── Derived: Latest Repair Results ─── */
  const latestRepairs = useMemo((): RepairResult[] => {
    if (!currentReviewId) return [];

    const matchingEvents = events.filter(
      (e) => e.type === "review_completed" && e.payload.review_id === currentReviewId
    );

    return matchingEvents.flatMap((e) => (e.payload.repair_results || []) as RepairResult[]);
  }, [events, currentReviewId]);

  return {
    socket,
    isConnected,
    events,
    clearEvents,
    agentStates,
    currentReview,
    currentReviewId,
    latestFindings,
    latestRepairs,
    metrics,
  };
}
