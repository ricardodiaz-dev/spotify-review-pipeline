import { sql, handle } from "./_db.js";
// Baseline ranking: priority = complaint_count x mean_severity = severity_sum; ties by issue_id.
export default (req, res) => handle(res, () => sql`SELECT * FROM spotify.issues ORDER BY rank`);
