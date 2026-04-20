// Clerk Core 3 middleware. Async auth.protect() for user-scoped routes.
// When Clerk keys are absent (demo/dev without an account) we no-op so the
// dashboard still loads. Alerts endpoints will 401 via FastAPI's own auth.
import { NextResponse } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const HAS_CLERK = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
const isProtected = createRouteMatcher(["/alerts(.*)"]);

export default HAS_CLERK
  ? clerkMiddleware(async (auth, req) => {
      if (isProtected(req)) {
        await auth.protect();
      }
    })
  : () => NextResponse.next();

export const config = {
  matcher: [
    // Skip Next.js internals and static files (standard Clerk matcher)
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
