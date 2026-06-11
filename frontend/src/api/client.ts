// Fetch-based API client with bearer token injection + automatic refresh rotation.
import { storage } from "@/src/utils/storage";

const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL ?? "") + "/api";

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

let accessToken: string | null = null;
let refreshToken: string | null = null;

// Tracks whether tokens have been hydrated from storage yet. Guards against a
// race on hard reload / deep-link where a screen fires an authenticated request
// before AuthProvider.bootstrap() has loaded the session (previously caused a
// spurious 403 + empty state). ensureSession() makes any authed request wait.
let sessionLoaded = false;
let loadingPromise: Promise<{ accessToken: string | null; refreshToken: string | null }> | null = null;

export async function loadSession() {
  accessToken = await storage.secureGet<string>(ACCESS_KEY, "");
  refreshToken = await storage.secureGet<string>(REFRESH_KEY, "");
  if (!accessToken) accessToken = null;
  if (!refreshToken) refreshToken = null;
  sessionLoaded = true;
  return { accessToken, refreshToken };
}

// Ensure tokens are read from storage exactly once before they're needed.
// Concurrent callers share the same in-flight promise.
async function ensureSession() {
  if (sessionLoaded) return;
  if (!loadingPromise) loadingPromise = loadSession();
  await loadingPromise;
}

export async function saveSession(access: string, refresh: string) {
  accessToken = access;
  refreshToken = refresh;
  sessionLoaded = true;
  await storage.secureSet(ACCESS_KEY, access);
  await storage.secureSet(REFRESH_KEY, refresh);
}

export async function clearSession() {
  accessToken = null;
  refreshToken = null;
  // Keep sessionLoaded = true: the session IS resolved (to "logged out"); we must
  // not re-read storage and resurrect stale tokens.
  sessionLoaded = true;
  await storage.secureRemove(ACCESS_KEY);
  await storage.secureRemove(REFRESH_KEY);
}

export function hasRefreshToken() {
  return !!refreshToken;
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function doRefresh(): Promise<boolean> {
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    await saveSession(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

async function request<T = any>(
  path: string,
  options: { method?: string; body?: any; auth?: boolean; _retry?: boolean } = {},
): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  // Wait for tokens to be hydrated from storage before attaching the auth header,
  // so requests fired during app startup / deep-link don't go out unauthenticated.
  if (auth) await ensureSession();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && auth && !options._retry) {
    const ok = await doRefresh();
    if (ok) return request<T>(path, { ...options, _retry: true });
    await clearSession();
    throw new ApiError("Session expired", 401);
  }

  let data: any = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const detail = (data && data.detail) || "Request failed";
    throw new ApiError(typeof detail === "string" ? detail : "Request failed", res.status);
  }
  return data as T;
}

export const api = {
  get: <T = any>(p: string) => request<T>(p, { method: "GET" }),
  post: <T = any>(p: string, body?: any, auth = true) =>
    request<T>(p, { method: "POST", body, auth }),
  put: <T = any>(p: string, body?: any) => request<T>(p, { method: "PUT", body }),
  del: <T = any>(p: string) => request<T>(p, { method: "DELETE" }),
};

export { ApiError };
