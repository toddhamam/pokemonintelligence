// Protected webhook invoked by the Python worker at end of daily pipeline.
// Uses Next.js 16 two-arg revalidateTag(tag, profile) — single-arg is deprecated.

import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";

const REVALIDATE_TOKEN = process.env.PIPELINE_REVALIDATE_TOKEN ?? "";

export async function POST(req: Request): Promise<Response> {
  const authz = req.headers.get("authorization") ?? "";
  if (!authz.toLowerCase().startsWith("bearer ") || REVALIDATE_TOKEN === "") {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const presented = authz.slice("bearer ".length).trim();
  if (presented !== REVALIDATE_TOKEN) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = (await req.json()) as { tags?: string[] };
  const tags = body.tags ?? [];
  for (const tag of tags) {
    // Next.js 16: two-arg form. "max" keeps the tag invalidated permanently until
    // re-populated on next fetch (single-arg revalidateTag is deprecated).
    revalidateTag(tag, "max");
  }
  return NextResponse.json({ invalidated: tags.length, tags });
}
