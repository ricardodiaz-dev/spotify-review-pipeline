## Recommendation

Prioritize **playback** next quarter, starting with `ISS-playback-playback_stops_or_skips` (Playback Stops or Skips), `ISS-playback-crash_or_wont_open` (App Crashes or Won't Open), and `ISS-playback-playback_other` (Other Playback Problems). Focus on reliability across starting, continuing, and controlling playback.

This is a deliberate choice over the baseline area ranking: playback is not the highest-ranked area by aggregate priority score, but its complaints more often describe serious disruption to listening. The recommendation is to address those core-task failures, not to infer a business outcome.

## Why

By the required baseline—priority score equals complaint count multiplied by mean severity—the highest-ranked issue is `ISS-other-general_negative` (General Negative Feedback), with **79,391** complaints [C001], mean severity **1.99** [C002], and priority score **157,846** [C003]. This broad category describes dissatisfaction without a specific fix, so it is not a directly actionable product workstream.

Among the listed product areas, **usability** ranks highest by priority score: **180,799** [A13], compared with billing/support at **173,862** [A19] and playback at **151,374** [A31]. Usability also has **73,854** complaints [A11]. Playback has fewer complaints, **45,694** [A29], but a higher mean severity, **3.31** [A32], and **15,691** severity **4–5** complaints [A33]. That concentration of high-severity reports supports a targeted playback investment despite its lower baseline area score.

Within playback, `ISS-playback-playback_stops_or_skips` has priority score **37,795** [C015], with **11,812** complaints [C013] and mean severity **3.20** [C014]. `ISS-playback-crash_or_wont_open` has priority score **26,216** [C021], with **6,868** complaints [C019] and mean severity **3.82** [C020]. `ISS-playback-playback_other` has priority score **21,257** [C030], with **6,238** complaints [C028] and mean severity **3.41** [C029]. Together, these signals favor work on interrupted listening and app availability over a broader usability program this quarter.

## Alternatives considered

- **Usability:** The strongest baseline area, with **73,854** complaints [A11] and priority score **180,799** [A13]. `ISS-usability-ads_interruptions` is its largest specified issue by count, at **36,257** complaints [C007], but mean severity is **2.13** [C008]. `ISS-usability-controls_shuffle_skip` is more severe on average, **2.97** [C011], with priority score **44,091** [C012]. I would reconsider usability if leadership chooses to follow aggregate priority score over concentrating on severe playback failures.
- **Billing/support:** It has **61,034** complaints [A17] and priority score **173,862** [A19]. `ISS-billing-free_tier_restrictions` alone has **48,031** complaints [C004] and priority score **140,647** [C006]. This is a substantial volume, but its area mean severity is **2.85** [A20], below playback’s **3.31** [A32].
- **Access:** Its **9,912** complaints [A41] and priority score **38,865** [A43] are lower, though mean severity is highest among the four areas at **3.92** [A44]. `ISS-access-login_failure` is serious, with priority score **28,532** [C018] and mean severity **3.95** [C017]. Access should move up if leadership prioritizes login blockage over the broader playback burden.

## Evidence

- `c30e8e8f-0790-4d25-b6a1-8f451285dc95` — Describes playback failing after an ad despite troubleshooting.
- `31d4742a-1c6c-4f9c-9679-77f259400986` — Reports songs and playlists failing to open.
- `6200035a-f8e9-4089-9414-9e0bce05660b` — Reports songs stopping unexpectedly.
- `47a1557c-36e8-4e7a-9b72-0a940c2ec715` — Describes being unable to log in and access saved music.
- `84300454-6a70-40f5-89bc-f9818dd4076d` — Objects to free-tier restrictions on listening and controls.

## Limitations

These are self-selected historical public reviews, not a representative sample of listeners. Model labels have measured error: verifier topic agreement was **84.1%** [A5], intent agreement **91.4%** [A6], and severity exact agreement **88.4%** [A7]; golden-sample topic agreement was **78.0%** [A8], with severity mean absolute error **0.24** [A10]. Cancellation language is stated intent, not observed churn. There is no revenue or plan data. **67** records were quarantined or unresolved [A3], including empty texts.
