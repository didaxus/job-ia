import { NextResponse } from "next/server";
// Legacy SQLite status authority disabled. The single global history in
// PostgreSQL lives at /api/applications and rejects duplicate job_url rows.
export async function POST() {
  return NextResponse.json({ error: "Use /api/applications (PostgreSQL)" }, {
    status: 410, headers: { "Cache-Control": "no-store" },
  });
}
export async function GET() {
  return NextResponse.json({ error: "Legacy endpoint retired" }, { status: 410 });
}
