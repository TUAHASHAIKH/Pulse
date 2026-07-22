"use client";

import styles from "./shared.module.css";

/**
 * A subtle CRT-style scanline overlay that adds sci-fi atmosphere.
 * Barely visible — just enough to evoke a terminal feeling.
 */
export function Scanline() {
  return <div className={styles.scanline} aria-hidden="true" />;
}
