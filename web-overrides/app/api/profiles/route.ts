import { NextResponse } from "next/server";
import { rows } from "@/lib/pg";
import { jsonError, knownProfile, rejectCrossOrigin } from "@/lib/security";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await rows(
      "SELECT id,label,headline,roles,search_terms,skills,summary,evidence,mode,languages,min_fit,cv_original_name,cv_uploaded_at,ai_opt_in,updated_at FROM search_profiles ORDER BY CASE id WHEN 'professional' THEN 0 ELSE 1 END"
    ), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return jsonError("Database unavailable", 503);
  }
}

function textList(v: unknown, max = 20): string[] | null {
  if (!Array.isArray(v) || v.length > max) return null;
  if (!v.every(x => typeof x === "string" && x.trim().length > 0 && x.length <= 100)) return null;
  return [...new Set(v.map(x => (x as string).trim()))];
}

export async function PATCH(req: Request) {
  const forbidden = rejectCrossOrigin(req);
  if (forbidden) return forbidden;
  let body: Record<string, unknown>;
  try { body = await req.json(); } catch { return jsonError("Malformed JSON"); }
  if (!knownProfile(body.id)) return jsonError("Unknown profile");
  const roles = textList(body.roles, 18);
  const searchTerms = textList(body.search_terms, 6);
  const skills = textList(body.skills, 30);
  const mode = body.mode;
  const langs = textList(body.languages, 2);
  const allowedLanguages = ["es", "en"];
  const minFit = body.min_fit;
  if (!roles || !roles.length || !searchTerms || !searchTerms.length || !skills || !langs || !langs.length ||
      !langs.every(l => allowedLanguages.includes(l)) ||
      !["remote", "hybrid", "both"].includes(String(mode)) ||
      !Number.isInteger(minFit) || Number(minFit) < 0 || Number(minFit) > 100 ||
      typeof body.headline !== "string" || body.headline.length > 160 ||
      typeof body.summary !== "string" || body.summary.length > 4000 ||
      typeof body.evidence !== "string" || body.evidence.length > 10000 ||
      typeof body.ai_opt_in !== "boolean") {
    return jsonError("Invalid profile fields or limits");
  }
  try {
    const sql = [
      "UPDATE search_profiles SET headline=$2,roles=$3,search_terms=$4,skills=$5,summary=$6,",
      "evidence=$7,mode=$8,languages=$9,min_fit=$10,ai_opt_in=$11,updated_at=now()",
      "WHERE id=$1 RETURNING id,label,headline,roles,search_terms,skills,summary,evidence,",
      "mode,languages,min_fit,cv_original_name,cv_uploaded_at,ai_opt_in,updated_at",
    ].join(" ");
    const updated = await rows(sql,
      [body.id, body.headline, roles, searchTerms, skills, body.summary, body.evidence,
       mode, langs, minFit, body.ai_opt_in]
    );
    return updated.length ? NextResponse.json(updated[0], {
      headers: { "Cache-Control": "no-store" },
    }) : jsonError("Profile does not exist", 404);
  } catch {
    return jsonError("Cannot save profile", 503);
  }
}
