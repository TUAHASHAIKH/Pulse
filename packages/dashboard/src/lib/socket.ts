"use client";

import { useEffect, useState } from "react";
import { io, Socket } from "socket.io-client";

// The shape of our agent results
export type Severity = "critical" | "warning" | "info";

export interface Finding {
  file: string;
  line: number;
  severity: Severity;
  category: string;
  title: string;
  explanation: string;
  suggested_fix?: string;
}

export interface AgentResult {
  agent_name: string;
  findings: Finding[];
  summary: string;
  token_usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  duration_seconds: number;
  error?: string;
}

// Event interfaces
export interface PulseEvent {
  id: string; // generated client-side for keys
  timestamp: number;
  type: 
    | "webhook_received" 
    | "review_started" 
    | "agent_started" 
    | "agent_completed" 
    | "review_completed";
  payload: any;
}

const ORCHESTRATOR_URL = "http://localhost:8000";

export function usePulseSocket() {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<PulseEvent[]>([]);

  useEffect(() => {
    // Connect to the orchestrator's Socket.io server mounted at /socket.io/
    const socketInstance = io(ORCHESTRATOR_URL, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
    });

    socketInstance.on("connect", () => {
      setIsConnected(true);
      console.log("Connected to Pulse Orchestrator");
    });

    socketInstance.on("disconnect", () => {
      setIsConnected(false);
      console.log("Disconnected from Pulse Orchestrator");
    });

    // Helper to add events to the timeline
    const addEvent = (type: PulseEvent["type"], payload: any) => {
      setEvents((prev) => [
        {
          id: Math.random().toString(36).substring(7),
          timestamp: Date.now(),
          type,
          payload,
        },
        ...prev,
      ]);
    };

    // Listen to all orchestrated events
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

  const clearEvents = () => setEvents([]);

  return { socket, isConnected, events, clearEvents };
}
