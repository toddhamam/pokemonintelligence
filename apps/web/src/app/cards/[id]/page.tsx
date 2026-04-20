// Card detail — price history chart + latest scores.
// Cache Components: the inner CardBody uses `use cache` + cacheTag for invalidation.
// `params` is a request-time input, so the outer page stays uncached and the
// cached body is rendered inside <Suspense> per Cache Components rules.

import { Suspense } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchCard, fetchCardPriceHistory, type PricePoint } from "@/lib/api";
import { PriceChart } from "./PriceChart";

export default async function CardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const cardId = Number.parseInt(id, 10);
  if (Number.isNaN(cardId)) return notFound();

  return (
    <Suspense fallback={<CardSkeleton />}>
      <CardBody cardId={cardId} />
    </Suspense>
  );
}

async function CardBody({ cardId }: { cardId: number }) {
  "use cache";
  const [card, prices] = await Promise.all([
    fetchCard(cardId),
    fetchCardPriceHistory(cardId),
  ]);
  const historyDepth = prices.length;
  const sources = Array.from(new Set(prices.map((p: PricePoint) => p.source)));

  return (
    <>
      <header className="miami-header">
        <div>
          <h1>
            {card.name} <span className="miami-subtitle">#{card.card_number}</span>
          </h1>
          <p className="miami-subtitle">
            {card.pokemon_name ?? "—"} · {card.rarity ?? "—"} ·
            <span className="miami-warmup">history: {historyDepth} days</span>
          </p>
        </div>
        <nav className="miami-subtitle">
          <Link href="/">← leaderboard</Link>
        </nav>
      </header>

      <div className="miami-detail-grid">
        <section className="miami-card">
          <h2 style={{ marginTop: 0 }}>Market price</h2>
          <p className="miami-subtitle">
            Sources: {sources.length ? sources.join(", ") : "none yet"}. PriceCharting is
            primary transaction truth; Pokémon TCG is a raw-card current anchor.
          </p>
          <PriceChart points={prices} />
        </section>
        <aside className="miami-card">
          <h2 style={{ marginTop: 0 }}>Notes</h2>
          <p className="miami-subtitle">
            History depth on this chart equals days since the pipeline began accumulating
            for this card. PriceCharting's API exposes current values only — no deep
            historical backfill. See plan §Phase 2 / Codex v2 review.
          </p>
        </aside>
      </div>
    </>
  );
}

function CardSkeleton() {
  return (
    <>
      <header className="miami-header">
        <h1 className="miami-subtitle">Loading card…</h1>
      </header>
      <section className="miami-card">
        <p className="miami-subtitle">Fetching price history.</p>
      </section>
    </>
  );
}
