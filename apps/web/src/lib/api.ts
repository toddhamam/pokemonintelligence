// Server-side FastAPI client. Runs only on the server — injects the bearer token
// from process.env so it never reaches the browser bundle.

import { cache } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SERVICE_TOKEN = process.env.FASTAPI_SERVICE_TOKEN ?? "";

type FetchOptions = {
  cacheTag?: string | string[];
  clerkUserId?: string;
  revalidate?: number | false;
};

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const url = `${API_URL}${path}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${SERVICE_TOKEN}`,
    Accept: "application/json",
  };
  if (options.clerkUserId) {
    headers["X-Clerk-User-Id"] = options.clerkUserId;
  }
  const tags = Array.isArray(options.cacheTag)
    ? options.cacheTag
    : options.cacheTag
      ? [options.cacheTag]
      : undefined;

  const res = await fetch(url, {
    headers,
    // Next.js 16 augments RequestInit with `next` for cache tagging — no ts suppress needed.
    next: tags ? { tags, revalidate: options.revalidate ?? 3600 } : undefined,
  });
  if (!res.ok) {
    throw new Error(`api_error ${res.status} ${path}`);
  }
  return (await res.json()) as T;
}

// ---- Typed thin wrappers. In production, all of these are regenerated from
// openapi-typescript. For now we hand-type the few shapes we use in v1 pages. ----

export type ScoresBlock = {
  breakout: number | null;
  arbitrage: number | null;
  long_term: number | null;
  confidence_raw: number;
  confidence_label: "High" | "Medium" | "Low" | "Experimental";
  label: string | null;
};

export type RankingRow = {
  entity_type: "card" | "sealed_product";
  entity_id: number;
  subject_variant: "raw" | "psa10" | "psa9" | "psa_other" | "sealed";
  name: string;
  set_name: string | null;
  scores: ScoresBlock;
  snapshot_date: string;
  explanations: string[];
};

export type PricePoint = {
  observed_date: string;
  source: string;
  market_price: number | null;
  low_price: number | null;
  high_price: number | null;
  confidence: number;
};

export type CardOut = {
  id: number;
  set_id: number;
  name: string;
  card_number: string;
  rarity: string | null;
  pokemon_name: string | null;
  language: string;
  is_promo: boolean;
  is_playable: boolean;
};

// React cache() de-dupes calls within a single request render pass.
export const fetchBreakouts = cache(async (): Promise<{ items: RankingRow[] }> => {
  return apiFetch("/v1/rankings/breakouts?limit=50&min_confidence=0", {
    cacheTag: ["rankings:breakouts"],
  });
});

export const fetchArbitrage = cache(async (): Promise<{ items: RankingRow[] }> => {
  return apiFetch("/v1/rankings/arbitrage?limit=50&min_confidence=0", {
    cacheTag: ["rankings:arbitrage"],
  });
});

export const fetchCard = cache(async (cardId: number): Promise<CardOut> => {
  return apiFetch(`/v1/cards/${cardId}`, { cacheTag: [`entity:card:${cardId}`] });
});

export const fetchCardPriceHistory = cache(
  async (cardId: number, source?: string): Promise<PricePoint[]> => {
    const q = source ? `?source=${source}` : "";
    return apiFetch(`/v1/cards/${cardId}/price-history${q}`, {
      cacheTag: [`entity:card:${cardId}`],
    });
  }
);
