import React, { createContext, useContext, useEffect, useState } from "react";
import { AppState, Platform } from "react-native";

import {
  flush,
  isFlushing,
  isOnline,
  loadQueue,
  pendingCount,
  setOnline,
  subscribe,
} from "./offlineQueue";

interface SyncState {
  online: boolean;
  pending: number;
  syncing: boolean;
  flushNow: () => void;
}

const SyncContext = createContext<SyncState>({
  online: true,
  pending: 0,
  syncing: false,
  flushNow: () => {},
});

export function useSync() {
  return useContext(SyncContext);
}

export function SyncProvider({ children }: { children: React.ReactNode }) {
  const [online, setOnlineState] = useState(true);
  const [pending, setPending] = useState(0);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      if (!mounted) return;
      setOnlineState(isOnline());
      setPending(pendingCount());
      setSyncing(isFlushing());
    };

    const unsub = subscribe(refresh);
    loadQueue().then(() => {
      refresh();
      void flush();
    });

    // Connectivity listeners
    const cleanups: (() => void)[] = [];
    if (Platform.OS === "web" && typeof window !== "undefined") {
      const goOnline = () => setOnline(true);
      const goOffline = () => setOnline(false);
      window.addEventListener("online", goOnline);
      window.addEventListener("offline", goOffline);
      setOnline(typeof navigator !== "undefined" ? navigator.onLine : true);
      cleanups.push(() => window.removeEventListener("online", goOnline));
      cleanups.push(() => window.removeEventListener("offline", goOffline));
    } else {
      // Native: flush when app returns to the foreground.
      const sub = AppState.addEventListener("change", (s) => {
        if (s === "active") void flush();
      });
      cleanups.push(() => sub.remove());
    }

    // Periodic retry (covers native where we lack OS connectivity events here).
    const interval = setInterval(() => {
      void flush();
      refresh();
    }, 20000);

    refresh();
    return () => {
      mounted = false;
      unsub();
      cleanups.forEach((c) => c());
      clearInterval(interval);
    };
  }, []);

  return (
    <SyncContext.Provider value={{ online, pending, syncing, flushNow: () => void flush() }}>
      {children}
    </SyncContext.Provider>
  );
}
