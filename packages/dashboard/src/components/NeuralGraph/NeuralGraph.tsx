"use client";

import { useRef, useEffect, useCallback } from "react";
import { AGENT_REGISTRY, ORCHESTRATOR_CONFIG } from "../../lib/agents";
import type { AgentRuntimeState } from "../../lib/socket";
import styles from "./NeuralGraph.module.css";

interface NeuralGraphProps {
  agentStates: Map<string, AgentRuntimeState>;
  isReviewActive: boolean;
}

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
const SPRING_K = 0.012;
const DAMPING = 0.88;
const HUB_SPRING_K = 0.04;
const HUB_DAMPING = 0.85;
const DRIFT_STRENGTH = 0.15;
const DRIFT_FREQ = 0.4;

export function NeuralGraph({ agentStates, isReviewActive }: NeuralGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const nodesRef = useRef<PhysicsNode[]>([]);
  const frameRef = useRef<number>(0);
  const initRef = useRef(false);

  // Drag interaction refs
  const draggedNodeRef = useRef<number | null>(null);
  const hoveredNodeRef = useRef<number | null>(null);
  const mouseRef = useRef({ x: 0, y: 0 });

  const computeTargets = useCallback((width: number, height: number) => {
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.38;
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

  const ensureNodes = useCallback((width: number, height: number) => {
    const targets = computeTargets(width, height);
    if (!initRef.current || nodesRef.current.length !== targets.length) {
      nodesRef.current = targets.map((t, i) => ({
        x: t.x + (Math.random() - 0.5) * 20,
        y: t.y + (Math.random() - 0.5) * 20,
        vx: 0,
        vy: 0,
        targetX: t.x,
        targetY: t.y,
        agentIndex: i - 1,
      }));
      initRef.current = true;
    } else {
      targets.forEach((t, i) => {
        nodesRef.current[i].targetX = t.x;
        nodesRef.current[i].targetY = t.y;
      });
    }
  }, [computeTargets]);

  const tickPhysics = useCallback((time: number) => {
    for (const node of nodesRef.current) {
      if (draggedNodeRef.current === node.agentIndex) {
        // Direct override for dragged node
        node.x = mouseRef.current.x;
        node.y = mouseRef.current.y;
        node.vx = 0;
        node.vy = 0;
        continue;
      }

      const isHub = node.agentIndex === -1;
      const k = isHub ? HUB_SPRING_K : SPRING_K;
      const damp = isHub ? HUB_DAMPING : DAMPING;

      const dx = node.targetX - node.x;
      const dy = node.targetY - node.y;
      const ax = dx * k;
      const ay = dy * k;

      const phase = (node.agentIndex + 1) * 1.618;
      const driftX = Math.sin(time * DRIFT_FREQ + phase) * DRIFT_STRENGTH * (isHub ? 0.3 : 1);
      const driftY = Math.cos(time * DRIFT_FREQ * 0.7 + phase * 1.3) * DRIFT_STRENGTH * (isHub ? 0.3 : 1);

      // Repulsion to make graph feel connected when dragging a node nearby
      let repX = 0;
      let repY = 0;
      if (draggedNodeRef.current !== null && !isHub) {
        const dragged = nodesRef.current.find(n => n.agentIndex === draggedNodeRef.current);
        if (dragged) {
          const rx = node.x - dragged.x;
          const ry = node.y - dragged.y;
          const distSq = rx * rx + ry * ry;
          if (distSq > 0 && distSq < 20000) { // Interaction radius squared
            const force = 80 / distSq;
            repX += rx * force;
            repY += ry * force;
          }
        }
      }

      node.vx = (node.vx + ax + driftX + repX) * damp;
      node.vy = (node.vy + ay + driftY + repY) * damp;

      node.x += node.vx;
      node.y += node.vy;
    }
  }, []);

  const draw = useCallback((ctx: CanvasRenderingContext2D, width: number, height: number, time: number) => {
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
        ctx.strokeStyle = "rgba(16, 185, 129, 0.6)";
        ctx.setLineDash([]);
      } else if (isPlanned) {
        ctx.strokeStyle = "rgba(107, 114, 128, 0.4)";
        ctx.setLineDash([4, 8]);
      } else {
        ctx.strokeStyle = "rgba(107, 114, 128, 0.6)";
        ctx.setLineDash([]);
      }

      ctx.lineWidth = isActive ? 2.5 : 1.5;
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

      ctx.beginPath();
      ctx.arc(px, py, 2, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = alpha * 0.9;
      ctx.fill();

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
    const hubGlowR = isReviewActive ? 40 : 20;

    const hg = ctx.createRadialGradient(hub.x, hub.y, 0, hub.x, hub.y, 36 * hubPulse + hubGlowR);
    hg.addColorStop(0, `rgba(168, 85, 247, ${isReviewActive ? 0.35 : 0.15})`);
    hg.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.beginPath();
    ctx.arc(hub.x, hub.y, 36 * hubPulse + hubGlowR, 0, Math.PI * 2);
    ctx.fillStyle = hg;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(hub.x, hub.y, 32 * hubPulse, 0, Math.PI * 2);
    ctx.fillStyle = "#0a0a0a";
    ctx.strokeStyle = ORCHESTRATOR_CONFIG.color;
    ctx.lineWidth = 2.5;
    ctx.fill();
    ctx.stroke();

    ctx.font = "10px 'Press Start 2P', monospace";
    ctx.fillStyle = ORCHESTRATOR_CONFIG.color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("ORCH", hub.x, hub.y);

    // ─── Agent nodes ───
    // Sort so the currently dragged node renders on top
    const sortedAgentNodes = [...agentNodes].sort((a, b) => {
      if (a.agentIndex === draggedNodeRef.current) return 1;
      if (b.agentIndex === draggedNodeRef.current) return -1;
      return 0;
    });

    sortedAgentNodes.forEach((node) => {
      const i = node.agentIndex;
      const agentConfig = AGENT_REGISTRY[i];
      const state = agentStates.get(agentConfig.id);
      const isActive = state?.status === "running";
      const isCompleted = state?.status === "completed";
      const isError = state?.status === "error";
      const isPlanned = agentConfig.status === "planned";
      const isDragged = draggedNodeRef.current === node.agentIndex;

      const baseR = 24;
      const R = isDragged ? baseR * 1.1 : baseR;
      const pulse = isActive ? 1 + Math.sin(time * 4) * 0.05 : 1;

      // Glow ring
      if (isActive || isCompleted || isDragged) {
        const glowSize = isDragged ? 32 : isActive ? 28 : 16;
        const gr = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, R + glowSize);
        gr.addColorStop(0, isDragged ? "rgba(255, 255, 255, 0.15)" : isActive ? agentConfig.colorDim : "rgba(16, 185, 129, 0.25)");
        gr.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.beginPath();
        ctx.arc(node.x, node.y, (R + glowSize) * pulse, 0, Math.PI * 2);
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
          ctx.globalAlpha = (1 - rp) * 0.35;
          ctx.lineWidth = 1.5;
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
      } else if (isDragged) {
        ctx.strokeStyle = "#ffffff";
      } else if (isActive) {
        ctx.strokeStyle = agentConfig.color;
      } else if (isCompleted) {
        ctx.strokeStyle = "#10b981";
      } else if (isPlanned) {
        ctx.strokeStyle = "rgba(107, 114, 128, 0.4)";
        ctx.globalAlpha = 0.7;
      } else {
        ctx.strokeStyle = "rgba(107, 114, 128, 0.7)";
      }
      ctx.lineWidth = isActive || isDragged ? 2.5 : 1.5;
      ctx.fill();
      ctx.stroke();
      ctx.globalAlpha = 1;

      // Short name
      ctx.font = "8px 'Press Start 2P', monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      if (isPlanned) ctx.globalAlpha = 0.6;
      ctx.fillStyle = isError
        ? "#ef4444"
        : isDragged
          ? "#ffffff"
          : isActive
            ? agentConfig.color
            : isCompleted
              ? "#10b981"
              : "#d4d4d8";
      ctx.fillText(agentConfig.shortName, node.x, node.y);
      ctx.globalAlpha = 1;

      // Status below
      if (state) {
        ctx.font = "13px system-ui, sans-serif";
        ctx.fillStyle = isError
          ? "rgba(239, 68, 68, 0.95)"
          : isActive
            ? "rgba(0, 240, 255, 0.95)"
            : "rgba(16, 185, 129, 0.95)";
        const label = isError ? "ERROR" : isActive ? "SCANNING" : `${state.duration?.toFixed(1)}s`;
        ctx.fillText(label, node.x, node.y + baseR + 20);
      }

      // Name above
      ctx.font = "14px system-ui, sans-serif";
      ctx.fillStyle = isPlanned ? "rgba(161, 161, 170, 0.7)" : isDragged ? "#ffffff" : "rgba(244, 244, 245, 0.9)";
      ctx.fillText(agentConfig.name.replace(" Agent", ""), node.x, node.y - baseR - 16);
    });

    ctx.restore();
  }, [agentStates, isReviewActive, ensureNodes, tickPhysics]);

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

    // Mouse Interaction Handlers
    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      mouseRef.current = { x: mx, y: my };

      if (draggedNodeRef.current === null) {
        let found = null;
        // Skip hub (index 0) to prevent dragging it
        for (let i = 1; i < nodesRef.current.length; i++) {
          const node = nodesRef.current[i];
          const dx = node.x - mx;
          const dy = node.y - my;
          if (dx * dx + dy * dy < 32 * 32) { // 32px hit radius
            found = node.agentIndex;
            break;
          }
        }
        hoveredNodeRef.current = found;
        canvas.style.cursor = found !== null ? 'grab' : 'default';
      } else {
        canvas.style.cursor = 'grabbing';
      }
    };

    const handleMouseDown = () => {
      if (hoveredNodeRef.current !== null) {
        draggedNodeRef.current = hoveredNodeRef.current;
        canvas.style.cursor = 'grabbing';
      }
    };

    const handleMouseUp = () => {
      draggedNodeRef.current = null;
      if (hoveredNodeRef.current !== null) {
        canvas.style.cursor = 'grab';
      } else {
        canvas.style.cursor = 'default';
      }
    };

    const handleMouseLeave = () => {
      draggedNodeRef.current = null;
      hoveredNodeRef.current = null;
      canvas.style.cursor = 'default';
    };

    canvas.addEventListener("mousemove", handleMouseMove);
    canvas.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mouseup", handleMouseUp);
    canvas.addEventListener("mouseleave", handleMouseLeave);

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
      canvas.removeEventListener("mousemove", handleMouseMove);
      canvas.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mouseup", handleMouseUp);
      canvas.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [draw]);

  return (
    <div className={styles.container} ref={containerRef}>
      <canvas ref={canvasRef} className={styles.canvas} />
    </div>
  );
}
