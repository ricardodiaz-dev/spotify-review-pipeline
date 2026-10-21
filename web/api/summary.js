import { sql, handle } from "./_db.js";
// Overall metrics: record accounting, area/topic aggregates, monthly trend, evaluation summaries.
export default (req, res) => handle(res, async () => {
  const [meta, areas, topics, trend] = await Promise.all([
    sql`SELECT k, v FROM spotify.run_meta`,
    sql`SELECT * FROM spotify.areas ORDER BY severity_sum DESC, product_area`,
    sql`SELECT * FROM spotify.topics ORDER BY severity_sum DESC, topic`,
    sql`SELECT data FROM spotify.monthly_trend ORDER BY month`,
  ]);
  return { meta: Object.fromEntries(meta.map(r => [r.k, r.v])), areas, topics, trend: trend.map(r => r.data) };
});
