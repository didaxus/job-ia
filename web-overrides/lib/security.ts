import { NextResponse } from "next/server";

// Additional same-origin check for cookie-authenticated mutating requests.
// Cloudflare Access JWT verification happens in proxy.ts.
export function rejectCrossOrigin(request: Request): NextResponse | null {
  const origin = request.headers.get("origin");
  const site = request.headers.get("sec-fetch-site");
  if (site === "cross-site") {
    return NextResponse.json({ error: "Cross-site request denied" }, { status: 403 });
  }
  if (origin) {
    let hostname = "";
    try {
      const url = new URL(origin);
      hostname = url.protocol === "https:" ? url.hostname : "";
    } catch { /* denied below */ }
    if (hostname !== "jobs-ia.didaxus.com") {
      return NextResponse.json({ error: "Untrusted Origin" }, { status: 403 });
    }
  }
  return null;
}

export function knownProfile(id: unknown): id is "professional" | "assistant" {
  return id === "professional" || id === "assistant";
}

export function jsonError(message: string, status = 400): NextResponse {
  return NextResponse.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
}
