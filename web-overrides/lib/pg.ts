import { Pool } from "pg";

// Runtime-only pool: postgres is the canonical store for both profiles.
// Credentials are injected by Coolify; they never enter the Docker image.
let pool: Pool | undefined;
function connection(): Pool {
  if (!process.env.PGPASSWORD) throw new Error("Database credentials are not configured");
  if (!pool) {
    pool = new Pool({
      host: process.env.PGHOST || "postgres",
      port: Number(process.env.PGPORT || 5432),
      database: process.env.PGDATABASE || "jobpilot",
      user: process.env.PGUSER || "jobpilot",
      password: process.env.PGPASSWORD,
      max: 6,
      connectionTimeoutMillis: 5000,
      idleTimeoutMillis: 30000,
    });
  }
  return pool;
}

export async function rows(sql: string, params: unknown[] = []): Promise<any[]> {
  const result = await connection().query(sql, params);
  return result.rows;
}
