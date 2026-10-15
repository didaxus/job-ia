import { NextResponse } from "next/server";
import { rows } from "@/lib/pg";
import { jsonError } from "@/lib/security";

// Status is operational metadata. Auth tokens never reach the dashboard.
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const current = await rows(
      "SELECT provider,state,checked_at FROM ai_runtime_status WHERE provider='codex_chatgpt'"
    );
    return NextResponse.json(
      current[0] || { provider:"codex_chatgpt", state:"login_required", checked_at:null },
      { headers: { "Cache-Control":"no-store" } },
    );
  } catch { return jsonError("Codex status unavailable", 503); }
}
