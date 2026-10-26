import { useCallback, useEffect, useRef, useState } from "react";

const POLL_MS = 2000;

/**
 * Start a pipeline refresh on the server and follow it until it ends.
 *
 * `job.state` is "idle", "running", "succeeded" or "failed" (the server's status plus, for a failed
 * start, an `error`). `onSucceeded` runs once when a refresh this page follows finishes. A refresh
 * that was already running when the page loaded is followed too, so a reload mid-run does not lose it.
 */
export function useRefresh(onSucceeded) {
  const [job, setJob] = useState({ state: "idle" });
  const timer = useRef(null);
  const following = useRef(false);
  const finished = useRef(onSucceeded);
  const again = useRef(() => {}); // poll again later; a ref so poll need not refer to itself

  useEffect(() => {
    finished.current = onSucceeded;
  }, [onSucceeded]);

  const poll = useCallback(async () => {
    try {
      const res = await fetch("/api/refresh/status", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const status = await res.json();
      if (status.state === "running") {
        following.current = true;
        setJob(status);
        timer.current = setTimeout(() => again.current(), POLL_MS);
      } else if (following.current) {
        following.current = false;
        setJob(status);
        if (status.state === "succeeded") finished.current();
      }
    } catch (err) {
      if (following.current) {
        following.current = false;
        setJob({ state: "failed", error: `Lost contact with the pipeline server (${err.message}).` });
      }
    }
  }, []);

  const start = useCallback(async () => {
    try {
      const res = await fetch("/api/refresh", { method: "POST" });
      const body = await res.json().catch(() => ({}));
      // 202 = started, 409 = one is already running; either way follow it
      if (res.status !== 202 && res.status !== 409) throw new Error(body.error || `HTTP ${res.status}`);
      following.current = true;
      setJob(body.state ? body : { state: "running" });
      timer.current = setTimeout(poll, POLL_MS);
    } catch (err) {
      setJob({
        state: "failed",
        error: `${err.message}. Is the pipeline server running? Start it with: python -m pipeline.server`,
      });
    }
  }, [poll]);

  useEffect(() => {
    again.current = poll;
    // pick up a refresh that is already running (the page was reloaded)
    timer.current = setTimeout(poll, 0);
    return () => clearTimeout(timer.current);
  }, [poll]);

  return { job, start };
}
