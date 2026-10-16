import { NextResponse } from "next/server";
import { rows } from "@/lib/pg";
import { jsonError, rejectCrossOrigin } from "@/lib/security";

export const dynamic = "force-dynamic";
const HEADERS = { "Cache-Control": "private, no-store" };

// Cloudflare Zero Trust protects the hostname outside this application.
// This handler does NOT accept or store ChatGPT credentials; only the
// short-lived device code created by the isolated pipeline worker.
export async function GET() {
  try {
    const latest = await rows([
      "SELECT id::text,state,",
      "CASE WHEN state='awaiting_user' AND expires_at>now() THEN verification_url ELSE NULL END AS verification_url,",
      "CASE WHEN state='awaiting_user' AND expires_at>now() THEN user_code ELSE NULL END AS user_code,",
      "CASE WHEN state IN ('queued','starting','awaiting_user') AND expires_at<=now() THEN 'expired' ELSE state END AS effective_state,",
      "CASE WHEN expires_at>now() THEN expires_at ELSE NULL END AS expires_at,",
      "error_code,created_at",
      "FROM codex_device_logins ORDER BY created_at DESC LIMIT 1",
    ].join(" "));
    return NextResponse.json(latest[0] || {
      id: null, state: "not_started", effective_state: "not_started",
      verification_url: null, user_code: null, expires_at: null, error_code: null,
    }, { headers: HEADERS });
  } catch {
    return jsonError("Codex login state unavailable: PostgreSQL schema is not ready", 503);
  }
}

export async function POST(request: Request) {
  const blocked = rejectCrossOrigin(request);
  if (blocked) return blocked;
  try {
    // Recover expired login sessions and enforce at most one active attempt.
    await rows([
      "UPDATE codex_device_logins SET state='expired', user_code=NULL,",
      "verification_url=NULL,error_code='expired',finished_at=now()",
      "WHERE state IN ('queued','starting','awaiting_user') AND expires_at<=now()",
    ].join(" "));
    const inserted = await rows([
      "INSERT INTO codex_device_logins(state) SELECT 'queued'",
      "WHERE NOT EXISTS (SELECT 1 FROM codex_device_logins",
      "WHERE state IN ('queued','starting','awaiting_user'))",
      "ON CONFLICT DO NOTHING RETURNING id::text,state,created_at",
    ].join(" "));
    const active = inserted.length ? inserted : await rows(
      "SELECT id::text,state,created_at FROM codex_device_logins WHERE state IN ('queued','starting','awaiting_user') ORDER BY created_at DESC LIMIT 1"
    );
    return NextResponse.json(active[0] || { state: "busy" }, {
      status: 202, headers: HEADERS,
    });
  } catch {
    return jsonError("Unable to create Codex authorization request", 503);
  }
}
