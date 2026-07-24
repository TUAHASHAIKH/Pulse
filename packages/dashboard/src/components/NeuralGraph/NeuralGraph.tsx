"use client";

import { useRef, useEffect, useCallback } from "react";
import { AGENT_REGISTRY, ORCHESTRATOR_CONFIG } from "../../lib/agents";
import type { AgentRuntimeState } from "../../lib/socket";
import styles from "./NeuralGraph.module.css";

interface NeuralGraphProps {
  agentStates: Map<string, AgentRuntimeState>;
  isReviewActive: boolean;
}

/** A physics node with position, velocity, and target. */
interface PhysicsNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetX: number;
  targetY: number;
  agentIndex: number; // -1 = orchestrator
}

interface Particle {
  progress: number;
  speed: number;
  nodeIndex: number;
}

// Spring physics constants
const SPRING_K = 0.012; // spring stiffness
const DAMPING = 0.88; // velocity damping
const HUB_SPRING_K = 0.04; // hub is stiffer
const HUB_DAMPING = 0.85;
const DRIFT_STRENGTH = 0.15; // random perturbation
const DRIFT_FREQ = 0.4; // how fast drift oscillates

export function NeuralGraph({ agentStates, isReviewActive }: NeuralGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const nodesRef = useRef<PhysicsNode[]>([]);
  const frameRef = useRef<number>(0);
  const initRef = useRef(false);

  /** Compute target positions (radial layout). */
  const computeTargets = useCallback((width: number, height: number) => {
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.3;
    const agents = AGENT_REGISTRY;
    const angleStep = (2 * Math.PI) / agents.length;
    const startAngle = -Math.PI / 2;

    const targets: { x: number; y: number }[] = [{ x: cx, y: cy }]; // hub
    agents.forEach((_, i) => {
      const angle = startAngle + i * angleStep;
      targets.push({
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
      });
    });
    return targets;
  }, []);

  /** Initialize physics nodes if not yet done. */
  const ensureNodes = useCallback(
    (width: number, height: number) => {
      const targets = computeTargets(width, height);

      if (!initRef.current || nodesRef.current.length !== targets.length) {
        nodesRef.current = targets.map((t, i) => ({
          x: t.x + (Math.random() - 0.5) * 20,
          y: t.y + (Math.random() - 0.5) * 20,
          vx: 0,
          vy: 0,
          targetX: t.x,
          targetY: t.y,
          agentIndex: i - 1, // -1 = hub, 0+ = agents
        }));
        initRef.current = true;
      } else {
        // Update targets on resize
        targets.forEach((t, i) => {
          nodesRef.current[i].targetX = t.x;
          nodesRef.current[i].targetY = t.y;
        });
      }
    },
    [computeTargets]
  );

  /** Run one physics tick. */
  const tickPhysics = useCallback((time: number) => {
    for (const node of nodesRef.current) {
      const isHub = node.agentIndex === -1;
      const k = isHub ? HUB_SPRING_K : SPRING_K;
      const damp = isHub ? HUB_DAMPING : DAMPING;

      // Spring force toward target
      const dx = node.targetX - node.x;
      const dy = node.targetY - node.y;
      const ax = dx * k;
      const ay = dy * k;

      // Organic drift — unique per node using sin with phase offsets
      const phase = (node.agentIndex + 1) * 1.618; // golden ratio spread
      const driftX =
        Math.sin(time * DRIFT_FREQ + phase) *
        DRIFT_STRENGTH *
        (isHub ? 0.3 : 1);
      const driftY =
        Math.cos(time * DRIFT_FREQ * 0.7 + phase * 1.3) *
        DRIFT_STRENGTH *
        (isHub ? 0.3 : 1);

      node.vx = (node.vx + ax + driftX) * damp;
      node.vy = (node.vy + ay + driftY) * damp;

      node.x += node.vx;
      node.y += node.vy;
    }
  }, []);

  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, width: number, height: number, time: number) => {
      const dpr = window.devicePixelRatio || 1;
      ctx.clearRect(0, 0, width * dpr, height * dpr);
      ctx.save();
      ctx.scale(dpr, dpr);

      ensureNodes(width, height);
      tickPhysics(time);

      const nodes = nodesRef.current;
      const hub = nodes[0];
      const agentNodes = nodes.slice(1);

      // ─── Draw connections ───
      agentNodes.forEach((node, i) => {
        const agentConfig = AGENT_REGISTRY[i];
        const state = agentStates.get(agentConfig.id);
        const isActive = state?.status === "running";
        const isCompleted = state?.status === "completed";
        const isError = state?.status === "error";
        const isPlanned = agentConfig.status === "planned";

        const midX = (hub.x + node.x) / 2;
        const midY = (hub.y + node.y) / 2;
        const offsetX = (node.y - hub.y) * 0.12;
        const offsetY = (hub.x - node.x) * 0.12;

        ctx.beginPath();
        ctx.moveTo(hub.x, hub.y);
        ctx.quadraticCurveTo(midX + offsetX, midY + offsetY, node.x, node.y);

        if (isError) {
          ctx.strokeStyle = `rgba(239, 68, 68, ${0.4 + Math.sin(time * 8) * 0.3})`;
          ctx.setLineDash([6, 8]);
        } else if (isActive) {
          ctx.strokeStyle = `${agentConfig.color}`;
          ctx.setLineDash([]);
        } else if (isCompleted) {
          ctx.strokeStyle = "rgba(16, 185, 129, 0.5)";
          ctx.setLineDash([]);
        } else if (isPlanned) {
          ctx.strokeStyle = "rgba(107, 114, 128, 0.2)";
          ctx.setLineDash([4, 8]);
        } else {
          ctx.strokeStyle = "rgba(107, 114, 128, 0.35)";
          ctx.setLineDash([]);
        }

        ctx.lineWidth = isActive ? 1.5 : 1;
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // ─── Particles ───
      const activeIndices = agentNodes
        .map((_, i) => i)
        .filter((i) => agentStates.get(AGENT_REGISTRY[i].id)?.status === "running");

      if (activeIndices.length > 0 && Math.random() < 0.18) {
        const idx = activeIndices[Math.floor(Math.random() * activeIndices.length)];
        particlesRef.current.push({
          progress: 0,
          speed: 0.006 + Math.random() * 0.008,
          nodeIndex: idx,
        });
      }

      particlesRef.current = particlesRef.current.filter((p) => {
        p.progress += p.speed;
        if (p.progress > 1) return false;

        const node = agentNodes[p.nodeIndex];
        if (!node) return false;

        const t = p.progress;
        const midX = (hub.x + node.x) / 2;
        const midY = (hub.y + node.y) / 2;
        const offsetX = (node.y - hub.y) * 0.12;
        const offsetY = (hub.x - node.x) * 0.12;

        const px = (1 - t) ** 2 * hub.x + 2 * (1 - t) * t * (midX + offsetX) + t ** 2 * node.x;
        const py = (1 - t) ** 2 * hub.y + 2 * (1 - t) * t * (midY + offsetY) + t ** 2 * node.y;

        const alpha = Math.sin(t * Math.PI);
        const color = AGENT_REGISTRY[p.nodeIndex].color;

        // Particle dot
        ctx.beginPath();
        ctx.arc(px, py, 2, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = alpha * 0.9;
        ctx.fill();

        // Soft glow
        ctx.beginPath();
        ctx.arc(px, py, 6, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = alpha * 0.12;
        ctx.fill();

        ctx.globalAlpha = 1;
        return true;
      });

      // ─── Hub node ───
      const hubPulse = 1 + Math.sin(time * 2) * 0.025;
      const hubGlowR = isReviewActive ? 28 : 16;

      // Glow
      const hg = ctx.createRadialGradient(hub.x, hub.y, 0, hub.x, hub.y, 24 * hubPulse + hubGlowR);
      hg.addColorStop(0, `rgba(168, 85, 247, ${isReviewActive ? 0.25 : 0.12})`);
      hg.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.beginPath();
      ctx.arc(hub.x, hub.y, 24 * hubPulse + hubGlowR, 0, Math.PI * 2);
      ctx.fillStyle = hg;
      ctx.fill();

      // Core
      ctx.beginPath();
      ctx.arc(hub.x, hub.y, 22 * hubPulse, 0, Math.PI * 2);
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

      // ─── Agent nodes ───
      agentNodes.forEach((node, i) => {
        const agentConfig = AGENT_REGISTRY[i];
        const state = agentStates.get(agentConfig.id);
        const isActive = state?.status === "running";
        const isCompleted = state?.status === "completed";
        const isError = state?.status === "error";
        const isPlanned = agentConfig.status === "planned";

        const R = 16;
        const pulse = isActive ? 1 + Math.sin(time * 4) * 0.05 : 1;

        // Glow ring
        if (isActive || isCompleted) {
          const gr = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, R + (isActive ? 20 : 12));
          gr.addColorStop(0, isActive ? agentConfig.colorDim : "rgba(16, 185, 129, 0.18)");
          gr.addColorStop(1, "rgba(0, 0, 0, 0)");
          ctx.beginPath();
          ctx.arc(node.x, node.y, (R + (isActive ? 20 : 12)) * pulse, 0, Math.PI * 2);
          ctx.fillStyle = gr;
          ctx.fill();
        }

        // Expand ring when running
        if (isActive) {
          const rp = (time * 1.5) % 2;
          if (rp < 1) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, R * (1 + rp * 1.5), 0, Math.PI * 2);
            ctx.strokeStyle = agentConfig.color;
            ctx.globalAlpha = (1 - rp) * 0.25;
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.globalAlpha = 1;
          }
        }

        // Body
        ctx.beginPath();
        ctx.arc(node.x, node.y, R * pulse, 0, Math.PI * 2);
        ctx.fillStyle = "#0a0a0a";
        if (isError) {
          ctx.strokeStyle = `rgba(239, 68, 68, ${0.5 + Math.sin(time * 8) * 0.3})`;
        } else if (isActive) {
          ctx.strokeStyle = agentConfig.color;
        } else if (isCompleted) {
          ctx.strokeStyle = "#10b981";
        } else if (isPlanned) {
          ctx.strokeStyle = "rgba(107, 114, 128, 0.25)";
          ctx.globalAlpha = 0.5;
        } else {
          ctx.strokeStyle = "rgba(107, 114, 128, 0.45)";
        }
        ctx.lineWidth = isActive ? 2 : 1;
        ctx.fill();
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Short name
        ctx.font = "6px 'Press Start 2P', monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        if (isPlanned) ctx.globalAlpha = 0.4;
        ctx.fillStyle = isError
          ? "#ef4444"
          : isActive
            ? agentConfig.color
            : isCompleted
              ? "#10b981"
              : "#a1a1aa";
        ctx.fillText(agentConfig.shortName, node.x, node.y);
        ctx.globalAlpha = 1;

        // Status below
        if (state) {
          ctx.font = "11px system-ui, sans-serif";
          ctx.fillStyle = isError
            ? "rgba(239, 68, 68, 0.85)"
            : isActive
              ? "rgba(0, 240, 255, 0.85)"
              : "rgba(16, 185, 129, 0.85)";
          const label = isError ? "ERROR" : isActive ? "SCANNING" : `${state.duration?.toFixed(1)}s`;
          ctx.fillText(label, node.x, node.y + R + 16);
        }

        // Name above
        ctx.font = "11px system-ui, sans-serif";
        ctx.fillStyle = isPlanned ? "rgba(107, 114, 128, 0.4)" : "rgba(228, 228, 231, 0.75)";
        ctx.fillText(agentConfig.name.replace(" Agent", ""), node.x, node.y - R - 12);
      });

      ctx.restore();
    },
    [agentStates, isReviewActive, ensureNodes, tickPhysics]
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
      const t = timestamp / 1000;
      const rect = container.getBoundingClientRect();
      draw(ctx, rect.width, rect.height, t);
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
      <canvas ref={canvasRef} className={styles.canvas} />
    </div>
  );
}
