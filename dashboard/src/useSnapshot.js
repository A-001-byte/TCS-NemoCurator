import { useEffect, useState } from "react";

/**
 * Load a JSON snapshot from the site root. status is "loading", "ready" or "missing"; a file that
 * is absent, is not JSON (a dev server answers a missing file with the page itself) or fails
 * `isValid` is "missing", so a panel can hide itself instead of breaking. A byte-order mark in the
 * file is ignored.
 */
export function useSnapshot(file, isValid = () => true) {
  const [state, setState] = useState({ status: "loading", data: null });

  useEffect(() => {
    let cancelled = false;
    fetch(`/${file}`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => JSON.parse(text.replace(/^﻿/, "")))
      .then((data) => {
        if (!isValid(data)) throw new Error("unexpected shape");
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "missing", data: null });
      });
    return () => {
      cancelled = true;
    };
  }, [file]); // eslint-disable-line react-hooks/exhaustive-deps -- isValid is a fixed function per file

  return state;
}
