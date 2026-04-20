// Alerts — placeholder page. Real CRUD lands after Clerk is configured (Phase 0).

import { Nav } from "../_components/Nav";

export default function AlertsPage() {
  const hasClerk = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
  return (
    <>
      <header className="miami-header">
        <div>
          <h1>Alerts</h1>
          <p className="miami-subtitle">
            Rule-based email alerts fire when a score crosses your threshold with
            sufficient confidence.
          </p>
        </div>
        <Nav />
      </header>

      <section className="miami-card">
        {hasClerk ? (
          <p className="miami-subtitle">
            Sign in to configure alerts. (Alert CRUD is Phase-6 work; the endpoints exist
            on FastAPI at <code>/v1/alerts</code> and are Clerk-gated.)
          </p>
        ) : (
          <>
            <p className="miami-subtitle">
              Clerk is not configured yet. To enable alerts:
            </p>
            <ol className="miami-subtitle">
              <li>Create a Clerk project at clerk.com.</li>
              <li>
                Add <code>NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code> and{" "}
                <code>CLERK_SECRET_KEY</code> to <code>apps/web/.env.local</code>.
              </li>
              <li>Restart the dev server. Sign-in links will appear in the nav.</li>
            </ol>
            <p className="miami-subtitle">
              FastAPI <code>/v1/alerts</code> endpoints are already implemented behind{" "}
              <code>require_clerk_user</code>; they return 401 until the Clerk user id is
              forwarded in the <code>X-Clerk-User-Id</code> header by Next.js.
            </p>
          </>
        )}
      </section>
    </>
  );
}
