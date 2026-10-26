/* Number formatting shared by every dashboard section. */

export const fmt = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : "–");
export const pct = (part, whole) => (whole ? `${((part / whole) * 100).toFixed(1)}%` : "–");
/** A 0..1 share as a percentage ("–" when there is no number). */
export const share = (value) => (typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "–");
/** Seconds as m:ss ("0:05", "12:34"). */
export const duration = (seconds) =>
  typeof seconds === "number" && seconds >= 0
    ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`
    : "–";
