import { NextResponse } from "next/server";
import { createHash, randomBytes } from "node:crypto";
import { readFile, mkdir, writeFile, rename, unlink } from "node:fs/promises";
import path from "node:path";
import { rows } from "@/lib/pg";
import { jsonError, knownProfile, rejectCrossOrigin } from "@/lib/security";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const dir = path.join(process.env.JOBPILOT_PRIVATE_DIR || "/opt/jobpilot/private", "cvs");
const MAX_PDF_BYTES = 5 * 1024 * 1024;

export async function POST(req: Request) {
  const forbidden = rejectCrossOrigin(req);
  if (forbidden) return forbidden;
  const form = await req.formData().catch(() => null);
  const id = form?.get("profile_id");
  const file = form?.get("file");
  if (!knownProfile(id) || !(file instanceof File) ||
      file.size === 0 || file.size > MAX_PDF_BYTES ||
      !file.name.toLowerCase().endsWith(".pdf")) {
    return jsonError("Attach a PDF up to 5 MB for Professional or Assistant");
  }
  const bytes = Buffer.from(await file.arrayBuffer());
  if (bytes.length < 8 || bytes.subarray(0, 5).toString("ascii") !== "%PDF-") {
    return jsonError("This file does not have a PDF header");
  }

  // Paths come from a closed set of two server-controlled profile IDs.
  const original = path.basename(file.name).replace(/[^\p{L}\p{N}._ -]/gu, "_").slice(0, 140);
  const target = path.join(dir, id + ".pdf");
  const tmp = path.join(dir, id + "." + randomBytes(8).toString("hex") + ".tmp");
  try {
    const present = await rows("SELECT id FROM search_profiles WHERE id=$1", [id]);
    if (!present.length) return jsonError("Profile not found", 404);
    await mkdir(dir, { recursive: true, mode: 0o700 });
    await writeFile(tmp, bytes, { flag: "wx", mode: 0o600 });
    await rename(tmp, target);
    await rows([
      "UPDATE search_profiles SET cv_original_name=$2,cv_sha256=$3,cv_uploaded_at=now(),updated_at=now()",
      "WHERE id=$1 RETURNING id",
    ].join(" "), [id, original, createHash("sha256").update(bytes).digest("hex")]);
    return NextResponse.json({ ok: true, filename: original, profile_id: id }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    await unlink(tmp).catch(() => {});
    return jsonError("Unable to store CV in private volume", 503);
  }
}

export async function GET(req: Request) {
  const id = new URL(req.url).searchParams.get("profile_id");
  if (!knownProfile(id)) return jsonError("Unknown profile");
  try {
    const found = await rows(
      "SELECT cv_sha256,cv_original_name FROM search_profiles WHERE id=$1",
      [id]
    );
    if (!found[0]?.cv_sha256) return jsonError("No CV uploaded", 404);
    const bytes = await readFile(path.join(dir, id + ".pdf"));
    if (createHash("sha256").update(bytes).digest("hex") !== found[0].cv_sha256) {
      return jsonError("Stored CV failed integrity check", 503);
    }
    return new NextResponse(new Uint8Array(bytes), {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": "attachment; filename=" + id + "-cv.pdf",
        "Cache-Control": "no-store, private",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return jsonError("CV unavailable", 503);
  }
}
