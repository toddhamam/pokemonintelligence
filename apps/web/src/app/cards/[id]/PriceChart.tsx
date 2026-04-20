"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PricePoint } from "@/lib/api";

export function PriceChart({ points }: { points: PricePoint[] }) {
  if (!points.length) {
    return (
      <p className="miami-subtitle">
        No price history yet — run the daily pipeline to seed this card's series.
      </p>
    );
  }

  // Recharts needs a flat series with numeric values; group by source.
  const bySource = new Map<string, { date: string; price: number }[]>();
  for (const p of points) {
    if (p.market_price === null) continue;
    const series = bySource.get(p.source) ?? [];
    series.push({ date: p.observed_date, price: Number(p.market_price) });
    bySource.set(p.source, series);
  }

  // Merge into a single array of {date, [source]: price}
  const dates = Array.from(new Set(points.map((p) => p.observed_date))).sort();
  const data = dates.map((d) => {
    const row: Record<string, number | string> = { date: d };
    for (const [source, series] of bySource.entries()) {
      const match = series.find((s) => s.date === d);
      if (match) row[source] = match.price;
    }
    return row;
  });

  const sources = Array.from(bySource.keys());
  const colors: Record<string, string> = {
    pricecharting: "#4ea9ff",
    pokemontcg: "#4ad69c",
    ebay: "#f1b24a",
  };

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <XAxis dataKey="date" stroke="#8a93a6" fontSize={11} />
          <YAxis stroke="#8a93a6" fontSize={11} width={48} />
          <Tooltip
            contentStyle={{
              background: "#11151d",
              border: "1px solid #1e2534",
              color: "#e6ebf2",
            }}
          />
          {sources.map((src) => (
            <Line
              key={src}
              type="monotone"
              dataKey={src}
              stroke={colors[src] ?? "#8a93a6"}
              strokeWidth={2}
              dot={{ r: 2 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
