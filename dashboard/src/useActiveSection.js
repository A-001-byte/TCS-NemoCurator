import { useEffect, useState } from "react";
import { ACTIVATION_LINE, chooseActive } from "./activeSection";

/* Events that mean the reader, not a link click, is moving the page. */
const READER_EVENTS = ["wheel", "touchmove", "keydown", "pointerdown"];

export function useActiveSection(ready, sections) {
  const [active, setActive] = useState(sections[0].id);

  useEffect(() => {
    if (!ready) return undefined;
    const ids = sections.map((s) => s.id);
    let pinned = null; // a clicked link wins until the reader scrolls
    let frame = 0;

    const update = () => {
      frame = 0;
      if (pinned) return;
      const tops = ids.map((id) => {
        const el = document.getElementById(id);
        return el ? el.getBoundingClientRect().top : null;
      });
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      setActive(chooseActive(ids, tops, window.innerHeight * ACTIVATION_LINE, atBottom));
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    const onHash = () => {
      const id = window.location.hash.slice(1);
      if (!ids.includes(id)) return;
      pinned = id;
      setActive(id);
    };
    const release = () => {
      pinned = null;
      schedule();
    };

    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("hashchange", onHash);
    READER_EVENTS.forEach((name) => window.addEventListener(name, release, { passive: true }));
    schedule();

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("hashchange", onHash);
      READER_EVENTS.forEach((name) => window.removeEventListener(name, release));
    };
  }, [ready, sections]);

  return active;
}
