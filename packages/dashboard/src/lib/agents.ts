/**
 * Agent Registry — Centralized agent configuration.
 *
 * Adding a new agent to the system? Just add an entry here.
 * The NeuralGraph, Timeline, and MetricsPanel all read from this registry,
 * so the UI automatically adapts with zero component changes.
 */

export type AgentStatus = "idle" | "running" | "completed" | "error";

export interface AgentConfig {
  id: string;
  name: string;
  shortName: string;
  icon: string; // lucide icon name
  color: string; // CSS color value
  colorDim: string; // CSS color value (low opacity)
  description: string;
  phase: number;
  status: "active" | "planned";
}

/**
 * The master list of all agents (active + planned).
 * The NeuralGraph renders active agents as bright nodes
 * and planned agents as dim, ghosted nodes.
 */
export const AGENT_REGISTRY: AgentConfig[] = [
  {
    id: "security",
    name: "Security Agent",
    shortName: "SEC",
    icon: "Shield",
    color: "#00f0ff",
    colorDim: "rgba(0, 240, 255, 0.15)",
    description: "Scans diffs for vulnerabilities: SQL injection, XSS, hardcoded secrets",
    phase: 2,
    status: "active",
  },
  {
    id: "performance",
    name: "Performance Agent",
    shortName: "PERF",
    icon: "Zap",
    color: "#f97316",
    colorDim: "rgba(249, 115, 22, 0.15)",
    description: "Detects N+1 queries, heavy renders, memory leaks",
    phase: 3,
    status: "active",
  },
  {
    id: "code_quality",
    name: "Code Quality Agent",
    shortName: "QUAL",
    icon: "Sparkles",
    color: "#a855f7",
    colorDim: "rgba(168, 85, 247, 0.15)",
    description: "Style violations, dead code, cyclomatic complexity",
    phase: 3,
    status: "active",
  },
  {
    id: "repair",
    name: "Repair Agent",
    shortName: "FIX",
    icon: "Wrench",
    color: "#10b981",
    colorDim: "rgba(16, 185, 129, 0.15)",
    description: "Auto-fixes critical findings in a Docker sandbox",
    phase: 4,
    status: "planned",
  },
  {
    id: "sentinel",
    name: "Sentinel Agent",
    shortName: "SNTL",
    icon: "Radar",
    color: "#3b82f6",
    colorDim: "rgba(59, 130, 246, 0.15)",
    description: "Kubernetes cluster monitoring & self-healing",
    phase: 7,
    status: "planned",
  },
];

/**
 * Quick lookup by agent ID.
 */
export function getAgentConfig(agentId: string): AgentConfig | undefined {
  return AGENT_REGISTRY.find((a) => a.id === agentId);
}

/**
 * Get the orchestrator node config (the central hub).
 */
export const ORCHESTRATOR_CONFIG = {
  id: "orchestrator",
  name: "Orchestrator",
  shortName: "ORCH",
  color: "#a855f7",
  colorDim: "rgba(168, 85, 247, 0.15)",
};
