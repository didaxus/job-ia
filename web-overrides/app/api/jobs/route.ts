import { NextResponse } from "next/server";
import { rows } from "@/lib/pg";
import { jsonError } from "@/lib/security";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const u = new URL(request.url);
  const selected = u.searchParams.get("profile") || "all";
  const includeRejected = u.searchParams.get("rejected") === "true";
  if (!["all", "professional", "assistant"].includes(selected)) {
    return jsonError("Unknown profile");
  }
  try {
    const jobs = await rows([
      "SELECT j.url,j.company,j.title,j.location,j.source,j.official_state,",
      "j.posted_at,j.description,pm.profile_id,sp.label AS profile_label,",
      "pm.title_relevance,pm.decision,pm.reason,pm.fit_score,pm.ai_summary,pm.ai_inferences,",
      "ah.status AS application_status,ah.notes AS application_notes,",
      "ah.origin AS application_origin",
      "FROM profile_matches pm JOIN jobs j ON j.url=pm.job_url",
      "JOIN search_profiles sp ON sp.id=pm.profile_id",
      "LEFT JOIN application_history ah ON ah.job_url=j.url",
      "WHERE ($1='all' OR pm.profile_id=$1)",
      "AND ($2=TRUE OR pm.decision<>'TITLE_NOT_RELEVANT')",
      "ORDER BY pm.title_relevance DESC,j.last_imported_at DESC LIMIT 400",
    ].join(" "), [selected, includeRejected]);
    return NextResponse.json(jobs, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return jsonError("Cannot load matches from PostgreSQL", 503);
  }
}
