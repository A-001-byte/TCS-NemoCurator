/* Small components shared by every dashboard section. */

export function SectionHeader({ title, description }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {description && <p className="section-desc">{description}</p>}
    </div>
  );
}

export function Bar({ value, max, tone = "primary" }) {
  const width = max ? Math.max((value / max) * 100, value > 0 ? 2 : 0) : 0;
  return (
    <div className="bar">
      <div className={`bar-fill fill-${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}
