import { useEffect, useState } from "react";

export function useActiveSection(ready, sections) {
  const [active, setActive] = useState(sections[0].id);
  useEffect(() => {
    if (!ready) return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((e) => e.isIntersecting);
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: "-30% 0px -60% 0px" }
    );
    sections.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [ready, sections]);
  return active;
}
