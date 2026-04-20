import "./globals.css";

import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";

export const metadata: Metadata = {
  title: "Miami — Pokemon Market Intelligence",
  description: "Daily decision engine for raw, graded, and sealed Pokemon cards.",
};

// ClerkProvider requires real keys at runtime. For dev/demo runs without Clerk
// configured, render the app without the provider so the dashboard is still
// browsable. Alerts/watchlists will be gated when keys are present.
const HAS_CLERK = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const body = <main className="miami-shell">{children}</main>;
  // Clerk Core 3: with Cache Components, ClerkProvider must be inside <body>, not
  // wrapping <html>. Without this the entire app becomes dynamic.
  return (
    <html lang="en">
      <body>{HAS_CLERK ? <ClerkProvider>{body}</ClerkProvider> : body}</body>
    </html>
  );
}
