import { sql, handle } from "./_db.js";
// AI-generated recommendation memo (memo role) + its code validation report and claim table.
export default (req, res) => handle(res, async () => {
  const [[memo], claims] = await Promise.all([
    sql`SELECT markdown, validation, input FROM spotify.memo WHERE id = 1`,
    sql`SELECT * FROM spotify.claims ORDER BY claim_id`,
  ]);
  return { ...memo, claims };
});
