import { sql, handle } from "./_db.js";
// Look up any source review by its original review_id.
export default (req, res) => handle(res, async () => {
  const id = String(req.query.id || "");
  const rows = await sql`SELECT * FROM spotify.records WHERE review_id = ${id}`;
  return rows[0] || { error: "not found" };
});
