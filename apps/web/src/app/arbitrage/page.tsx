// Arbitrage leaderboard — grading EV for raw → PSA-10.

import { fetchArbitrage } from "@/lib/api";
import { Nav } from "../_components/Nav";
import { RankingTable } from "../_components/RankingTable";

export default async function ArbitragePage() {
  "use cache";
  const { items } = await fetchArbitrage();
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <header className="miami-header">
        <div>
          <h1>Grading arbitrage</h1>
          <p className="miami-subtitle">
            as of {today} · raw → PSA-10 expected value, net of fees · confidence-capped
            when signal is eBay-dominated
          </p>
        </div>
        <Nav />
      </header>

      <section className="miami-card">
        <RankingTable
          rows={items}
          scoreKey="arbitrage"
          scoreLabel="EV / $ raw"
          emptyHint={
            "No arbitrage scores yet. Run the daily pipeline to populate grading EV inputs from PriceCharting + PSA population."
          }
        />
      </section>
    </>
  );
}
