import Link from "next/link";

export function Nav() {
  return (
    <nav className="miami-subtitle">
      <Link href="/">Breakouts</Link>
      {" · "}
      <Link href="/arbitrage">Arbitrage</Link>
      {" · "}
      <Link href="/alerts">Alerts</Link>
    </nav>
  );
}
