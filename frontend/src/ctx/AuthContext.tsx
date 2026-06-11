import * as LocalAuthentication from "expo-local-authentication";
import { useRouter, useSegments } from "expo-router";
import React, {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { Platform } from "react-native";

import {
  api,
  clearSession,
  hasRefreshToken,
  loadSession,
  saveSession,
} from "@/src/api/client";
import { storage } from "@/src/utils/storage";

type User = { id: string; email: string; full_name?: string | null };

type AuthContextType = {
  user: User | null;
  loading: boolean;
  locked: boolean;
  biometricEnabled: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (
    email: string,
    password: string,
    fullName: string,
  ) => Promise<{ verification_required?: boolean; email?: string; detail?: string }>;
  verifyEmail: (email: string, code: string) => Promise<void>;
  resendVerification: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  tryUnlock: () => Promise<boolean>;
  setBiometricEnabled: (v: boolean) => Promise<void>;
};

const BIO_KEY = "biometric_enabled";
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Fire-and-forget weekly auto-backup check. Runs at most once per app session;
// the backend no-ops when a recent (<7 day) auto-backup already exists and never
// touches the user's manual backups.
let weeklyBackupChecked = false;
function ensureWeeklyBackup() {
  if (weeklyBackupChecked) return;
  weeklyBackupChecked = true;
  api.post("/backups/ensure-weekly", {}).catch(() => {
    // Allow a retry later in the session if this attempt failed (e.g. offline).
    weeklyBackupChecked = false;
  });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [biometricEnabled, setBiometricState] = useState(false);

  useEffect(() => {
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function bootstrap() {
    try {
      const { refreshToken } = await loadSession();
      const bioOn = await storage.getItem<boolean>(BIO_KEY, false);
      setBiometricState(!!bioOn);

      if (!refreshToken) {
        setLoading(false);
        return;
      }

      // If biometric is enabled and supported, lock until unlocked.
      if (bioOn && Platform.OS !== "web") {
        const hasHardware = await LocalAuthentication.hasHardwareAsync();
        const enrolled = await LocalAuthentication.isEnrolledAsync();
        if (hasHardware && enrolled) {
          setLocked(true);
          setLoading(false);
          // still fetch user behind the lock screen
          await fetchUser();
          return;
        }
      }
      await fetchUser();
    } finally {
      setLoading(false);
    }
  }

  async function fetchUser() {
    try {
      const me = await api.get<User>("/auth/me");
      setUser(me);
      ensureWeeklyBackup();
    } catch {
      await clearSession();
      setUser(null);
    }
  }

  async function signIn(email: string, password: string) {
    const data = await api.post("/auth/login", { email, password }, false);
    await saveSession(data.access_token, data.refresh_token);
    const me = await api.get<User>("/auth/me");
    setUser(me);
    setLocked(false);
  }

  async function signUp(email: string, password: string, fullName: string) {
    // Email-verification flow: register no longer auto-logs in. It creates an
    // unverified account and emails a code; the caller routes to the verify screen.
    return await api.post(
      "/auth/register",
      { email, password, full_name: fullName },
      false,
    );
  }

  async function verifyEmail(email: string, code: string) {
    const data = await api.post("/auth/verify-email", { email, code }, false);
    await saveSession(data.access_token, data.refresh_token);
    const me = await api.get<User>("/auth/me");
    setUser(me);
    setLocked(false);
  }

  async function resendVerification(email: string) {
    await api.post("/auth/resend-verification", { email }, false);
  }

  async function signOut() {
    try {
      await api.post("/auth/logout");
    } catch {
      /* ignore network errors */
    }
    await clearSession();
    setUser(null);
    setLocked(false);
  }

  async function tryUnlock(): Promise<boolean> {
    if (Platform.OS === "web") {
      setLocked(false);
      return true;
    }
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: "Unlock Cycle",
      fallbackLabel: "Use passcode",
    });
    if (result.success) {
      setLocked(false);
      if (!user) await fetchUser();
      return true;
    }
    return false;
  }

  async function setBiometricEnabled(v: boolean) {
    await storage.setItem(BIO_KEY, v);
    setBiometricState(v);
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        locked,
        biometricEnabled,
        signIn,
        signUp,
        verifyEmail,
        resendVerification,
        signOut,
        tryUnlock,
        setBiometricEnabled,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// Route protection hook
export function useProtectedRoute() {
  const { user, loading, locked } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    const inAuthGroup = segments[0] === "(auth)";
    const onUnlock = segments[0] === "unlock";

    if (locked && !onUnlock) {
      router.replace("/unlock");
    } else if (!locked && !user && !inAuthGroup) {
      router.replace("/(auth)/login");
    } else if (!locked && user && (inAuthGroup || onUnlock)) {
      router.replace("/(tabs)");
    }
  }, [user, loading, locked, segments, router]);
}
