import { NextRequest, NextResponse } from "next/server";
import { createRemoteJWKSet, jwtVerify } from "jose";

// Next.js 16 uses proxy.ts. Signed Cloudflare Access JWT is REQUIRED:
// Tunnel forwarding or unverified identity headers are not authentication.
export async function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (path.startsWith("/_next/") || path === "/favicon.ico" || path === "/healthz") {
    return NextResponse.next();
  }
  const noCache = { "Cache-Control": "no-store" };
  const issuer = (process.env.CF_ACCESS_TEAM_DOMAIN || "").replace(/\/+$/, "");
  const audience = process.env.CF_ACCESS_AUD || "";
  if (!/^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/i.test(issuer) || !audience) {
    return new NextResponse("Cloudflare Access is not configured", { status: 503, headers: noCache });
  }
  const token = request.headers.get("cf-access-jwt-assertion") ||
    request.cookies.get("CF_Authorization")?.value;
  if (!token) {
    return new NextResponse("Cloudflare Access authentication required", {
      status: 401, headers: noCache,
    });
  }
  try {
    const jwks = createRemoteJWKSet(new URL(issuer + "/cdn-cgi/access/certs"));
    const verified = await jwtVerify(token, jwks, {
      issuer, audience, algorithms: ["RS256"], clockTolerance: 30,
    });
    // Do not accept organization-wide sessions or service tokens for this private UI.
    if (verified.payload.type !== "app" || typeof verified.payload.email !== "string" ||
        !verified.payload.email.includes("@")) throw new Error("Human Access session required");
    return NextResponse.next();
  } catch {
    return new NextResponse("Invalid or expired Cloudflare Access token", {
      status: 401, headers: noCache,
    });
  }
}

export const config = { matcher: "/:path*" };
