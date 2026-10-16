import { NextResponse } from "next/server";
import { rows } from "@/lib/pg";

export const dynamic = "force-dynamic";

// Read-only, deliberately restricted operational status: no DB credentials,
// stack traces, candidate personal information or device codes.
export async function GET() {
  try {
    const exists = await rows([
      "SELECT",
      "to_regclass('public.search_profiles') IS NOT NULL AS profiles,",
      "to_regclass('public.jobs') IS NOT NULL AS jobs,",
      "to_regclass('public.search_requests') IS NOT NULL AS searches,",
      "to_regclass('public.worker_heartbeat') IS NOT NULL AS heartbeat",
    ].join(" "));
    const ready = exists[0]?.profiles && exists[0]?.jobs && exists[0]?.searches;
    if (!ready) {
      return NextResponse.json({
        database: "schema_missing", worker: "unknown", jobs: null,
        message: "Database connected; schema initialization incomplete",
      }, { status: 503, headers: { "Cache-Control": "no-store" } });
    }
    const counts = await rows([
      "SELECT (SELECT count(*)::integer FROM jobs) AS jobs,",
      "(SELECT count(*)::integer FROM search_profiles) AS profiles,",
      "(SELECT count(*)::integer FROM profile_matches) AS matches",
    ].join(" "));
    let worker: "active" | "stale" | "unknown" = "unknown";
    if (exists[0].heartbeat) {
      const beats = await rows([
        "SELECT (checked_at > now()-interval '90 seconds') AS active",
        "FROM worker_heartbeat WHERE worker_id='pipeline'",
      ].join(" "));
      worker = beats[0]?.active ? "active" : "stale";
    }
    return NextResponse.json({
      database: "ready", worker,
      jobs: counts[0]?.jobs ?? 0,
      profiles: counts[0]?.profiles ?? 0,
      matches: counts[0]?.matches ?? 0,
      message: worker === "stale"
        ? "PostgreSQL available, but pipeline worker has no recent heartbeat"
        : "Operational status available",
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({
      database: "unavailable", worker: "unknown", jobs: null,
      message: "Unable to connect to PostgreSQL: check database container and credentials",
    }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
