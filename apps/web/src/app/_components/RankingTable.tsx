// Shared leaderboard table. Server-component safe — no interactive state.

import Link from "next/link";
import type { RankingRow } from "@/lib/api";

type Props = {
  rows: RankingRow[];
  scoreKey: "breakout" | "arbitrage" | "long_term";
  scoreLabel: string;
  emptyHint: string;
};

export function RankingTable({ rows, scoreKey, scoreLabel, emptyHint }: Props) {
  if (!rows.length) {
    return <p className="miami-subtitle">{emptyHint}</p>;
  }
  return (
    <table className="miami-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Card / Product</th>
          <th>Set</th>
          <th>Variant</th>
          <th>{scoreLabel}</th>
          <th>Confidence</th>
          <th>Label</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, idx) => {
          const value = row.scores[scoreKey];
          return (
            <tr key={`${row.entity_type}-${row.entity_id}-${row.subject_variant}`}>
              <td>{idx + 1}</td>
              <td>
                <Link href={linkFor(row)}>{row.name}</Link>
                {warmingUpBadge(row)}
              </td>
              <td className="miami-subtitle">{row.set_name ?? "—"}</td>
              <td className="miami-subtitle">{row.subject_variant}</td>
              <td className={`miami-score ${(value ?? 0) >= 0 ? "pos" : "neg"}`}>
                {formatScore(value)}
              </td>
              <td>
                <span className={`miami-badge ${row.scores.confidence_label.toLowerCase()}`}>
                  {row.scores.confidence_label}
                </span>{" "}
                <span className="miami-subtitle">
                  {row.scores.confidence_raw.toFixed(2)}
                </span>
              </td>
              <td className="miami-subtitle">{row.scores.label ?? "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function linkFor(row: RankingRow): string {
  if (row.entity_type === "card") return `/cards/${row.entity_id}`;
  return `/sealed/${row.entity_id}`;
}

function formatScore(s: number | null): string {
  if (s === null || Number.isNaN(s)) return "—";
  return s.toFixed(3);
}

function warmingUpBadge(row: RankingRow): React.ReactNode {
  const clamped = row.explanations.some((e) => e.includes("confidence_clamped_to_medium"));
  if (!clamped) return null;
  return <span className="miami-warmup">warming up</span>;
}
