"use client";

import { useRef, useEffect, useCallback } from "react";
import { AGENT_REGISTRY, ORCHESTRATOR_CONFIG } from "../../lib/agents";
import type { AgentRuntimeState } from "../../lib/socket";
import styles from "./NeuralGraph.module.css";

interface NeuralGraphProps {
  agentStates: Map<string, AgentRuntimeState>;
  isReviewActive: boolean;
}

interface NodePosition {
  x: number;
  y: number;
  agent: (typeof AGENT_REGISTRY)[number] | typeof ORCHESTRATOR_CONFIG;
  isOrchestrator: boolean;
}

interface Particle {
  progress: number;  // 0 to 1 along the connection
  speed: number;
  nodeIndex: number; // which agent connection this particle is on
}

export function NeuralGraph({ agentStates, isReviewActive }: NeuralGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const frameRef = useRef<number>(0);
  const timeRef = useRef<number>(0);

  const getNodePositions = useCallback(
    (width: number, height: number): NodePosition[] => {
      const cx = width / 2;
      const cy = height / 2;
      const radius = Math.min(width, height) * 0.32;

      const positions: NodePosition[] = [
        {
          x: cx,
          y: cy,
          agent: ORCHESTRATOR_CONFIG as any,
          isOrchestrator: true,
        },
      ];

      const agents = AGENT_REGISTRY;
      const angleStep = (2 * Math.PI) / agents.length;
      const startAngle = -Math.PI / 2; // start from top

      agents.forEach((agent, i) => {
        const angle = startAngle + i * angleStep;
        positions.push({
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
          agent,
          isOrchestrator: false,
        });
      });

      return positions;
    },
    []
  );

  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, width: number, height: number, time: number) => {
      const dpr = window.devicePixelRatio || 1;
      ctx.clearRect(0, 0, width * dpr, height * dpr);
      ctx.save();
      ctx.scale(dpr, dpr);

      const positions = getNodePositions(width, height);
      const hub = positions[0];
      const agents = positions.slice(1);

      // ─── Draw connections ───
      agents.forEach((node, i) => {
        const agentConfig = node.agent as (typeof AGENT_REGISTRY)[number];
        const state = agentStates.get(agentConfig.id);
        const isActive = state?.status === "running";
        const isCompleted = state?.status === "completed";
        const isError = state?.status === "error";
        const isPlanned = agentConfig.status === "planned";

        // Connection line
        ctx.beginPath();
        ctx.moveTo(hub.x, hub.y);

        // Curved bezier connection
        const midX = (hub.x + node.x) / 2;
        const midY = (hub.y + node.y) / 2;
        const offsetX = (node.y - hub.y) * 0.15;
        const offsetY = (hub.x - node.x) * 0.15;

        ctx.quadraticCurveTo(midX + offsetX, midY + offsetY, node.x, node.y);

        if (isError) {
          ctx.strokeStyle = `rgba(239, 68, 68, ${0.4 + Math.sin(time * 8) * 0.3})`;
          ctx.setLineDash([6, 8]);
        } else if (isActive) {
          ctx.strokeStyle = agentConfig.color;
          ctx.setLineDash([]);
        } else if (isCompleted) {
          ctx.strokeStyle = `rgba(16, 185, 129, 0.6)`;
          ctx.setLineDash([]);
        } else if (isPlanned) {
          ctx.strokeStyle = "rgba(63, 63, 70, 0.3)";
          ctx.setLineDash([4, 8]);
        } else {
          ctx.strokeStyle = "rgba(63, 63, 70, 0.5)";
          ctx.setLineDash([]);
        }

        ctx.lineWidth = isActive ? 2 : 1;
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // ─── Draw particles (flowing along connections when agents are active) ───
      const activeAgentIndices = agents
        .map((node, i) => ({
          index: i,
          agent: node.agent as (typeof AGENT_REGISTRY)[number],
        }))
        .filter(({ agent }) => {
          const state = agentStates.get(agent.id);
          return state?.status === "running";
        });

      // Spawn new particles for active agents
      if (activeAgentIndices.length > 0 && Math.random() < 0.15) {
        const target =
          activeAgentIndices[Math.floor(Math.random() * activeAgentIndices.length)];
        particlesRef.current.push({
          progress: 0,
          speed: 0.008 + Math.random() * 0.008,
          nodeIndex: target.index,
        });
      }

      // Update and draw particles
      particlesRef.current = particlesRef.current.filter((p) => {
        p.progress += p.speed;
        if (p.progress > 1) return false;

        const node = agents[p.nodeIndex];
        if (!node) return false;

        const t = p.progress;
        const midX = (hub.x + node.x) / 2;
        const midY = (hub.y + node.y) / 2;
        const offsetX = (node.y - hub.y) * 0.15;
        const offsetY = (hub.x - node.x) * 0.15;

        // Quadratic bezier interpolation
        const px =
          (1 - t) * (1 - t) * hub.x +
          2 * (1 - t) * t * (midX + offsetX) +
          t * t * node.x;
        const py =
          (1 - t) * (1 - t) * hub.y +
          2 * (1 - t) * t * (midY + offsetY) +
          t * t * node.y;

        const alpha = Math.sin(t * Math.PI); // fade in/out
        const agentConfig = node.agent as (typeof AGENT_REGISTRY)[number];

        ctx.beginPath();
        ctx.arc(px, py, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = agentConfig.color;
        ctx.globalAlpha = alpha * 0.9;
        ctx.fill();

        // Glow effect
        ctx.beginPath();
        ctx.arc(px, py, 6, 0, Math.PI * 2);
        ctx.fillStyle = agentConfig.color;
        ctx.globalAlpha = alpha * 0.15;
        ctx.fill();

        ctx.globalAlpha = 1;
        return true;
      });

      // ─── Draw nodes ───

      // Hub node (orchestrator)
      const hubPulse = 1 + Math.sin(time * 2) * 0.03;
      const hubGlow = isReviewActive ? 24 : 12;

      // Hub outer glow
      const hubGradient = ctx.createRadialGradient(
        hub.x, hub.y, 0,
        hub.x, hub.y, 28 * hubPulse + hubGlow
      );
      hubGradient.addColorStop(0, `rgba(168, 85, 247, ${isReviewActive ? 0.3 : 0.15})`);
      hubGradient.addColorStop(1, "transparent");
      ctx.beginPath();
      ctx.arc(hub.x, hub.y, 28 * hubPulse + hubGlow, 0, Math.PI * 2);
      ctx.fillStyle = hubGradient;
      ctx.fill();

      // Hub core
      ctx.beginPath();
      ctx.arc(hub.x, hub.y, 20 * hubPulse, 0, Math.PI * 2);
      ctx.fillStyle = "#0a0a0a";
      ctx.strokeStyle = ORCHESTRATOR_CONFIG.color;
      ctx.lineWidth = 2;
      ctx.fill();
      ctx.stroke();

      // Hub label
      ctx.font = "7px 'Press Start 2P', monospace";
      ctx.fillStyle = ORCHESTRATOR_CONFIG.color;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("ORCH", hub.x, hub.y);

      // Agent nodes
      agents.forEach((node) => {
        const agentConfig = node.agent as (typeof AGENT_REGISTRY)[number];
        const state = agentStates.get(agentConfig.id);
        const isActive = state?.status === "running";
        const isCompleted = state?.status === "completed";
        const isError = state?.status === "error";
        const isPlanned = agentConfig.status === "planned";

        const nodeRadius = 16;
        const pulse = isActive ? 1 + Math.sin(time * 4) * 0.06 : 1;

        // Outer glow
        if (isActive || isCompleted) {
          const glowSize = isActive ? 20 : 12;
          const gradient = ctx.createRadialGradient(
            node.x, node.y, 0,
            node.x, node.y, nodeRadius + glowSize
          );
          if (isActive) {
            // Use the agent's colorDim (already has low alpha)
            gradient.addColorStop(0, agentConfig.colorDim);
          } else {
            gradient.addColorStop(0, "rgba(16, 185, 129, 0.2)");
          }
          gradient.addColorStop(1, "rgba(0, 0, 0, 0)");
          ctx.beginPath();
          ctx.arc(node.x, node.y, (nodeRadius + glowSize) * pulse, 0, Math.PI * 2);
          ctx.fillStyle = gradient;
          ctx.fill();
        }

        // Ring expand animation when active
        if (isActive) {
          const ringPhase = (time * 1.5) % 2;
          if (ringPhase < 1) {
            const ringScale = 1 + ringPhase * 1.5;
            const ringAlpha = 1 - ringPhase;
            ctx.beginPath();
            ctx.arc(node.x, node.y, nodeRadius * ringScale, 0, Math.PI * 2);
            ctx.strokeStyle = agentConfig.color;
            ctx.globalAlpha = ringAlpha * 0.3;
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.globalAlpha = 1;
          }
        }

        // Node body
        ctx.beginPath();
        ctx.arc(node.x, node.y, nodeRadius * pulse, 0, Math.PI * 2);
        ctx.fillStyle = "#0a0a0a";

        if (isError) {
          ctx.strokeStyle = `rgba(239, 68, 68, ${0.5 + Math.sin(time * 8) * 0.3})`;
        } else if (isActive) {
          ctx.strokeStyle = agentConfig.color;
        } else if (isCompleted) {
          ctx.strokeStyle = "#10b981";
        } else if (isPlanned) {
          ctx.strokeStyle = "rgba(63, 63, 70, 0.3)";
          ctx.globalAlpha = 0.4;
        } else {
          ctx.strokeStyle = "rgba(63, 63, 70, 0.6)";
        }

        ctx.lineWidth = isActive ? 2 : 1;
        ctx.fill();
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Node label
        ctx.font = "6px 'Press Start 2P', monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        if (isPlanned) {
          ctx.globalAlpha = 0.3;
        }

        ctx.fillStyle = isError
          ? "#ef4444"
          : isActive
            ? agentConfig.color
            : isCompleted
              ? "#10b981"
              : "#71717a";
        ctx.fillText(agentConfig.shortName, node.x, node.y);
        ctx.globalAlpha = 1;

        // Status text below node
        if (state) {
          ctx.font = "10px var(--font-mono), monospace";
          ctx.fillStyle = isError
            ? "rgba(239, 68, 68, 0.7)"
            : isActive
              ? "rgba(0, 240, 255, 0.7)"
              : "rgba(16, 185, 129, 0.7)";
          const statusLabel = isError
            ? "ERROR"
            : isActive
              ? "SCANNING"
              : `${state.duration?.toFixed(1)}s`;
          ctx.fillText(statusLabel, node.x, node.y + nodeRadius + 14);
        }

        // Agent name above node
        ctx.font = "10px system-ui, sans-serif";
        ctx.fillStyle = isPlanned
          ? "rgba(113, 113, 122, 0.3)"
          : "rgba(228, 228, 231, 0.6)";
        ctx.fillText(agentConfig.name.replace(" Agent", ""), node.x, node.y - nodeRadius - 10);
      });

      ctx.restore();
    },
    [agentStates, isReviewActive, getNodePositions]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = container.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    const animate = (timestamp: number) => {
      timeRef.current = timestamp / 1000;
      const rect = container.getBoundingClientRect();
      draw(ctx, rect.width, rect.height, timeRef.current);
      frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frameRef.current);
      observer.disconnect();
    };
  }, [draw]);

  return (
    <div className={styles.container} ref={containerRef}>
      <div className={styles.label}>
        <span className={styles.labelText}>AGENT NETWORK</span>
      </div>
      <canvas ref={canvasRef} className={styles.canvas} />
    </div>
  );
}
