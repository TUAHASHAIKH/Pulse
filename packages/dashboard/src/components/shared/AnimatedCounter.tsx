"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./shared.module.css";

interface AnimatedCounterProps {
  value: number;
  duration?: number;
  className?: string;
  prefix?: string;
  suffix?: string;
}

export function AnimatedCounter({
  value,
  duration = 800,
  className = "",
  prefix = "",
  suffix = "",
}: AnimatedCounterProps) {
  const [displayValue, setDisplayValue] = useState(0);
  const prevValue = useRef(0);
  const animationRef = useRef<number | null>(null);

  useEffect(() => {
    const start = prevValue.current;
    const end = value;
    const startTime = performance.now();

    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(start + (end - start) * eased);

      setDisplayValue(current);

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      } else {
        prevValue.current = end;
      }
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [value, duration]);

  return (
    <span className={`${styles.animatedCounter} ${className}`}>
      {prefix}
      {displayValue.toLocaleString()}
      {suffix}
    </span>
  );
}
