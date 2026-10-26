import { reasonLabel } from "../stages";
import { Bar } from "../components/common";
import { fmt, pct } from "../format";

export default function ReasonList({ rows, total, label = reasonLabel }) {
  const max = total ?? Math.max(...rows.map(([, v]) => v), 0);
  return (
    <ul className="reason-list">
      {rows.map(([key, count]) => (
        <li key={key}>
          <div className="reason-row">
            <span>{label(key)}</span>
            <span className="num">
              {fmt(count)}
              {total ? <span className="muted"> · {pct(count, total)}</span> : null}
            </span>
          </div>
          <Bar value={count} max={max} />
        </li>
      ))}
    </ul>
  );
}
