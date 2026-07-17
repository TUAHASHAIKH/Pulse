"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Inbox } from "lucide-react";
import { EventCard } from "./EventCard";
import type { PulseEvent } from "../lib/socket";
import styles from "./LiveFeed.module.css";

export function LiveFeed({ events }: { events: PulseEvent[] }) {
  if (events.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Inbox size={48} className={styles.emptyIcon} />
        <h3>Waiting for activity...</h3>
        <p>Open a PR or run a CLI review to see events here.</p>
      </div>
    );
  }

  return (
    <div className={styles.feedContainer}>
      <AnimatePresence initial={false}>
        {events.map((event) => (
          <motion.div
            key={event.id}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
            layout
          >
            <EventCard event={event} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
