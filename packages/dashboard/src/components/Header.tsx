import { Activity } from "lucide-react";
import styles from "./Header.module.css";

export function Header({ isConnected }: { isConnected: boolean }) {
  return (
    <header className={styles.header}>
      <div className={styles.logo}>
        <Activity className={styles.logoIcon} size={28} />
        <span>Pulse Dashboard</span>
      </div>
      
      <div className={styles.status}>
        <div className={`${styles.dot} ${isConnected ? styles.connected : ''}`} />
        <span>{isConnected ? "Connected to Orchestrator" : "Disconnected"}</span>
      </div>
    </header>
  );
}
