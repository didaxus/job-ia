import { NextResponse } from "next/server";
import { rows } from "@/lib/pg";
import { jsonError, knownProfile, rejectCrossOrigin } from "@/lib/security";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await rows(
      "SELECT id,profile_id,kind,state,created_at,started_at,finished_at,error_message FROM search_requests ORDER BY id DESC LIMIT 15"
    ), { headers: { "Cache-Control": "no-store" } });
  } catch { return jsonError("Cannot load search history", 503); }
}

export async function POST(req: Request) {
  const forbidden = rejectCrossOrigin(req);
  if (forbidden) return forbidden;
  const body = await req.json().catch(() => null);
  const pid = body?.profile_id ?? null;
  if (pid !== null && !knownProfile(pid)) return jsonError("Unknown profile");
  try {
    const created = await rows([
      "INSERT INTO search_requests(profile_id,kind,state)",
      "SELECT $1,'fetch','queued'",
      "WHERE NOT EXISTS (SELECT 1 FROM search_requests WHERE state IN ('queued','running'))",
      "ON CONFLICT DO NOTHING RETURNING id,state,created_at",
    ].join(" "), [pid]);
    if (!created.length) return jsonError("A search is already running or queued", 409);
    return NextResponse.json(created[0], {
      status: 202, headers: { "Cache-Control": "no-store" },
    });
  } catch { return jsonError("Cannot queue new search", 503); }
}
