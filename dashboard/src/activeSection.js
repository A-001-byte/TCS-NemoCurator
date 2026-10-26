/* Which sidebar link is highlighted: a pure decision, so it can be tested without a browser. */

/* The highlight moves to a section once its top has passed this fraction of the window height. */
export const ACTIVATION_LINE = 0.3;

/**
 * @param {string[]} ids section ids, top to bottom
 * @param {(number|null)[]} tops each section's distance from the top of the window (null if it is not on the page)
 * @param {number} line the activation line, in pixels from the top of the window
 * @param {boolean} atBottom true when the page cannot scroll any further
 * @returns {string} the id to highlight
 */
export function chooseActive(ids, tops, line, atBottom) {
  if (atBottom) {
    // The last sections can never reach the activation line; at the end of the page the last one wins.
    return ids[ids.length - 1];
  }
  let current = ids[0];
  ids.forEach((id, i) => {
    if (tops[i] !== null && tops[i] <= line) current = id;
  });
  return current;
}
