// Offline write queue with conflict-safe replay.
//
// Strategy:
//  - Mutating writes go through `syncWrite()`. Each carries a client-generated
//    `client_id` so the backend can dedupe replays (idempotent writes).
//  - If the device is offline (or the network request fails), the op is persisted
//    to a queue and retried later (on reconnect / app foreground / interval).
//  - Server-rejected writes (HTTP 4xx, except 401) are NOT queued/retried — they are
//    permanent client errors and would otherwise poison the queue.
//  - Conflict resolution: the backend is the source of truth. Idempotency keys prevent
//    duplicates; date-keyed upserts (daily logs) are naturally last-write-wins.

import { storage } from "@/src/utils/storage";
import { api, ApiError } from "@/src/api/client";

const QUEUE_KEY = "offline_write_queue_v1";

export type QueueMethod = "POST" | "PUT" | "DELETE";

export interface QueuedOp {
  id: string; // == client_id
  method: QueueMethod;
  path: string;
  body?: any;
  label: string; // human-readable, e.g. "Water +250ml"
  createdAt: number;
  tries: number;
}

let queue: QueuedOp[] = [];
let loaded = false;
let flushing = false;
let online = true;
let forcedOffline = false;

const listeners = new Set<() => void>();

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function emit() {
  listeners.forEach((fn) => fn());
}

function uuid(): string {
  return (
    "op-" +
    Date.now().toString(36) +
    "-" +
    Math.random().toString(36).slice(2, 10)
  );
}

function detectOnline(): boolean {
  if (forcedOffline) return false;
  if (typeof navigator !== "undefined" && typeof navigator.onLine === "boolean") {
    return navigator.onLine;
  }
  return online;
}

/** Diagnostics: force the queue to treat the device as offline. */
export function setForcedOffline(value: boolean) {
  forcedOffline = value;
  emit();
  if (!value) void flush();
}
export function getForcedOffline(): boolean {
  return forcedOffline;
}

async function persist() {
  await storage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

export async function loadQueue() {
  if (loaded) return;
  const raw = await storage.getItem<string>(QUEUE_KEY, "[]");
  try {
    queue = raw ? JSON.parse(raw) : [];
  } catch {
    queue = [];
  }
  if (!Array.isArray(queue)) queue = [];
  loaded = true;
  emit();
}

export function getQueue(): QueuedOp[] {
  return [...queue];
}
export function pendingCount(): number {
  return queue.length;
}
export function isFlushing(): boolean {
  return flushing;
}
export function isOnline(): boolean {
  return detectOnline();
}

export function setOnline(value: boolean) {
  const changed = online !== value;
  online = value;
  if (changed) emit();
  if (value) void flush();
}

async function enqueue(op: QueuedOp) {
  queue.push(op);
  await persist();
  emit();
}

/**
 * Perform a mutating write that is resilient to being offline.
 * Returns { queued, data }. When queued, the write will be retried automatically.
 */
export async function syncWrite<T = any>(
  method: QueueMethod,
  path: string,
  body: any,
  label: string,
): Promise<{ queued: boolean; data?: T }> {
  await loadQueue();
  const client_id = uuid();
  const payload = { ...(body || {}), client_id };

  if (detectOnline()) {
    try {
      const data = await call<T>(method, path, payload);
      return { queued: false, data };
    } catch (e) {
      if (e instanceof ApiError) {
        // Server responded. 5xx -> queue & retry. 4xx (incl. auth) -> surface error.
        if (e.status >= 500) {
          await enqueue({ id: client_id, method, path, body: payload, label, createdAt: Date.now(), tries: 1 });
          return { queued: true };
        }
        throw e;
      }
      // Network error -> queue for later.
    }
  }
  await enqueue({ id: client_id, method, path, body: payload, label, createdAt: Date.now(), tries: 0 });
  return { queued: true };
}

function call<T>(method: QueueMethod, path: string, payload: any): Promise<T> {
  if (method === "POST") return api.post<T>(path, payload);
  if (method === "PUT") return api.put<T>(path, payload);
  return api.del<T>(path);
}

/**
 * Flush the queue (FIFO). Stops on the first network/5xx error to preserve ordering;
 * drops permanent 4xx errors so they can't block the queue forever.
 */
export async function flush(): Promise<void> {
  await loadQueue();
  if (flushing || !detectOnline() || queue.length === 0) return;
  flushing = true;
  emit();
  try {
    while (queue.length > 0 && detectOnline()) {
      const op = queue[0];
      try {
        await call(op.method, op.path, op.body);
        queue.shift();
        await persist();
        emit();
      } catch (e) {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 401) {
          // permanent client error -> drop to avoid a poison op blocking the queue
          queue.shift();
          await persist();
          emit();
          continue;
        }
        // network error, 401 (token not ready), or 5xx -> retry later
        op.tries += 1;
        await persist();
        break;
      }
    }
  } finally {
    flushing = false;
    emit();
  }
}

/** Test/debug helper. */
export async function clearQueue() {
  queue = [];
  await persist();
  emit();
}
