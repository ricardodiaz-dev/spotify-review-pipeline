## Recommendation

Prioritise **billing/support**, beginning with `ISS-billing-free_tier_restrictions` (Free-Tier Feature Restrictions). Make the first workstream a review of free-tier limits and their in-product explanation; pair it with diagnosis of the remaining billing/support complaints before committing to additional fixes. The evidence identifies one billing/support issue in detail, so it does not support naming two more specific issue-level fixes.

This recommendation differs from the historical area priority-score ranking: usability ranks highest overall. Billing/support is the better next-quarter bet because its share of classified complaints is much higher at the end of the review window than in the comparison window. Treat that rise as an association in self-selected reviews, not evidence that product changes caused it.

## Why

Under the required baseline—priority score equals complaint count multiplied by mean severity—the highest-ranked issue is `ISS-other-general_negative` (General Negative Feedback): 79,391 complaints [C001], mean severity 1.99 [C002], and priority score 157,846 [C003]. This broad category has the highest issue score, but does not point to a specific fix. Among actionable named issues, `ISS-billing-free_tier_restrictions` (Free-Tier Feature Restrictions) scores 140,647 [C006], on 48,031 complaints [C004] with mean severity 2.93 [C005].

At area level, usability ranks highest by priority score at 180,799 [A32], ahead of billing/support at 173,862 [A38]. Usability also has more complaints: 73,854 [A30] versus 61,034 [A36]. But the end-of-window trend favors billing/support: in Aug-Oct 2022, it accounted for 3,415 complaints, or 4.0% of 85,236 completed classified reviews [A11, A16, A17]; in Aug-Oct 2023, it accounted for 34,414 complaints, or 21.4% of 161,173 completed classified reviews [A20, A25, A26]. Usability’s share was 11.1% of 85,236 reviews in the earlier period [A11, A14], and 12.4% of 161,173 in the later period [A20, A23]. This supports investigating billing/support now, while recognizing that different denominators and self-selection limit interpretation.

The free-tier issue has substantial volume and higher mean severity than broad general negativity. Representative reviews describe limits on selecting, repeating, and listening to playlist songs; they signal friction around access to core listening features, not merely dissatisfaction with pricing.

## Alternatives considered

- **Usability:** Baseline area priority-score leader, with 73,854 complaints [A30] and 180,799 priority score [A32]. `ISS-usability-ads_interruptions` (Frequent Ad Interruptions) has a priority score of 77,273 [C009], and `ISS-usability-controls_shuffle_skip` (Shuffle and Playback Controls) scores 44,091 [C012]. Reconsider usability if targeted work on these issues is more feasible or if subsequent evidence shows billing/support’s recent share was transient.
- **Playback:** Has the highest area mean severity among these areas at 3.31 [A51], and 15,691 severity 4-5 complaints [A52]. Yet its share fell from 7.5% of 85,236 reviews [A11, A12] to 5.1% of 161,173 reviews [A20, A21]. `ISS-playback-playback_stops_or_skips` (Playback Stops or Skips) scores 37,795 [C015]. Keep reliability work in view, but the trend argues against making it the primary area.
- **Access:** Severe when it occurs: mean severity 3.92 [A63], with 8,686 severity 4-5 complaints [A64]. Its share moved from 1.1% of 85,236 reviews [A11, A18] to 2.0% of 161,173 [A20, A27]. `ISS-access-login_failure` (Unable to Log In) scores 28,532 [C018]. Prioritise if operational monitoring indicates a broader access incident.

## Evidence

- `84300454-6a70-40f5-89bc-f9818dd4076d` — objects that many features now require Premium.
- `cba5ab8b-0bbb-45b8-8925-b6d843d12d42` — describes losing song selection and repeat controls.
- `5785e125-8b06-4318-acbd-f215ba170fe8` — reports unwanted shuffle and difficulty playing a chosen playlist.
- `47a1557c-36e8-4e7a-9b72-0a940c2ec715` — describes repeated login failure and inaccessible saved music.

## Limitations

These are self-selected historical public reviews, not a representative customer sample. Model labels have measured error: verifier topic agreement was 84.1% [A5], intent agreement 91.4% [A6], and severity exact agreement 88.4% [A7]; golden-set topic agreement was 78.0% [A8] and severity mean absolute error was 0.24 [A10]. Cancellation language is stated intent, not observed churn. There is no revenue or plan data. The records include 67 quarantined or unresolved items, including empty texts [A3]. The Aug-Oct comparison excludes partial 2023-11 [A29].
