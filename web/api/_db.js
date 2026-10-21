import { neon } from "@neondatabase/serverless";
// Read-only queries against the processed pipeline outputs stored in Neon Postgres (schema `spotify`).
export const sql = neon(process.env.DATABASE_URL);
export function send(res, body, status = 200) {
  res.status(status).setHeader("Content-Type", "application/json");
  res.send(JSON.stringify(body));
}
export async function handle(res, fn) {
  try { send(res, await fn()); } catch (e) { send(res, { error: String(e.message || e) }, 500); }
}
