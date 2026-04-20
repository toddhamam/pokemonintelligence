// Dashboard — breakout leaderboard.

import { fetchBreakouts } from "@/lib/api";
import { Nav } from "./_components/Nav";
import { RankingTable } from "./_components/RankingTable";

export default async function DashboardPage() {
  "use cache";
  const { items } = await fetchBreakouts();
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <header className="miami-header">
        <div>
          <h1>Breakout leaderboard</h1>
          <p className="miami-subtitle">
            as of {today} · transaction-truth signals live · eBay signals warming up until v1b
          </p>
        </div>
        <Nav />
      </header>

      <section className="miami-card">
        <RankingTable
          rows={items}
          scoreKey="breakout"
          scoreLabel="Breakout"
          emptyHint={
            "No scores yet. Run `python -m miami_api.worker.daily_pipeline` to seed the pipeline, or wait for the next scheduled run."
          }
        />
      </section>
    </>
  );
}
