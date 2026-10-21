import { sql, handle } from "./_db.js";
// One issue with its severity distribution and highest-severity member reviews (traceable review IDs).
export default (req, res) => handle(res, async () => {
  const id = String(req.query.id || "");
  const limit = Math.min(parseInt(req.query.limit || "25", 10) || 25, 100);
  const [issue] = await sql`SELECT * FROM spotify.issues WHERE issue_id = ${id}`;
  if (!issue) return { error: "unknown issue" };
  const [dist, reviews, claims] = await Promise.all([
    sql`SELECT severity, intent, COUNT(*)::int AS n FROM spotify.records WHERE issue_id = ${id} GROUP BY severity, intent ORDER BY severity, intent`,
    sql`SELECT review_id, severity, intent, sentiment, needs_review, evidence_quote, review_text, review_timestamp, review_rating, cache_source_id
        FROM spotify.records WHERE issue_id = ${id} AND cache_source_id = '' ORDER BY severity DESC, needs_review, review_id LIMIT ${limit}`,
    sql`SELECT * FROM spotify.claims WHERE issue_id = ${id} ORDER BY claim_id`,
  ]);
  return { issue, dist, reviews, claims };
});
