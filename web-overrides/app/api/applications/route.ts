import { NextResponse } from "next/server";
import { rows } from "@/lib/pg";
import { jsonError, knownProfile, rejectCrossOrigin } from "@/lib/security";

const STATUSES = ["saved","applied_reported","interview","rejected","skipped","no_response"];
export async function POST(req: Request) {
  const forbidden = rejectCrossOrigin(req);
  if (forbidden) return forbidden;
  const body = await req.json().catch(() => null);
  if (!body || typeof body.url !== "string" || !body.url.startsWith("https://") ||
      body.url.length > 2048 || !knownProfile(body.profile_id) ||
      !STATUSES.includes(body.status) ||
      typeof body.notes !== "string" || body.notes.length > 4000) {
    return jsonError("Invalid application status");
  }
  try {
    const result = await rows([
      "INSERT INTO application_history(job_url,profile_id,status,notes,origin)",
      "VALUES ($1,$2,$3,$4,'manual')",
      "ON CONFLICT (job_url) DO UPDATE SET",
      "profile_id=excluded.profile_id,status=excluded.status,",
      "notes=excluded.notes,origin='manual',updated_at=now()",
      "RETURNING job_url,status,updated_at",
    ].join(" "), [body.url,body.profile_id,body.status,body.notes]);
    return NextResponse.json(result[0], { headers: { "Cache-Control": "no-store" } });
  } catch {
    return jsonError("Cannot save status (job must exist)", 503);
  }
}
