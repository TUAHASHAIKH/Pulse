"use client";

import styles from "./shared.module.css";

interface GlowDotProps {
  color?: string;
  mode?: "pulse" | "breathe" | "flicker" | "solid";
  size?: number;
}

export function GlowDot({
  color = "var(--nx-emerald)",
  mode = "pulse",
  size = 8,
}: GlowDotProps) {
  const animClass =
    mode === "pulse"
      ? styles.dotPulse
      : mode === "breathe"
        ? styles.dotBreathe
        : mode === "flicker"
          ? styles.dotFlicker
          : "";

  return (
    <span
      className={`${styles.glowDot} ${animClass}`}
      style={
        {
          "--dot-color": color,
          width: size,
          height: size,
        } as React.CSSProperties
      }
    />
  );
}
