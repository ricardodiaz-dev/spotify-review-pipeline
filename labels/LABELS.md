# Shared label definitions, examples and output schema

These are the course's common labels (GRADING_CONTRACT.md) plus this project's optional subtopics and worked examples. The enrichment prompt [`prompts/enrich_v1.md`](../prompts/enrich_v1.md) contains the same rules. Only the review text is a classification input. Stars, likes, app version and timestamp are metadata used for analysis.

## Topic (exactly one)
| topic | definition | subtopics (used for issue grouping) |
|---|---|---|
| access | login, signup, password, account access | login_failure, account_lost_or_hacked, signup_verification, unexpected_logout, access_other |
| usability | navigation, controls, layout, queue/playlist management, ad interruptions | ads_interruptions, ui_layout_redesign, queue_playlist_management, controls_shuffle_skip, usability_other |
| playback | playback failure, crashes, lag, connection failures, audio quality, resource use | crash_or_wont_open, playback_stops_or_skips, lag_slow_or_freeze, connection_error, audio_quality, device_integration, battery_resource_use, playback_other |
| downloads | downloading, saved music, offline listening, disappearing downloads | downloads_disappearing, download_failure, offline_mode, downloads_other |
| catalog | missing songs/artists, search/discovery, recommendations, lyrics availability | missing_or_removed_content, search_discovery, recommendations_repetitive, lyrics, podcasts_audiobooks, catalog_other |
| billing | price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls | free_tier_restrictions, premium_price, charges_refunds, subscription_activation, billing_other |
| support | contacting support and the support response | support_unresponsive, support_other |
| other | general praise/criticism, unrelated content, no specific supported topic | general_negative, general_positive, unrelated_or_political, other_misc |

Choose the problem with the highest supported severity, and on a tie the first one mentioned. For praise, choose the first specific praised feature. Generic praise is `other`. Mentioning premium alone does not make a review `billing`. Code keeps topic and subtopic consistent: if the model returns a subtopic from a different topic, code maps it to `<topic>_other` and records the reason.

## Intent (precedence order)
`cancellation` (explicitly leaving, uninstalling, cancelling, switching, or threatening to) > `complaint` (any negative experience, including mixed reviews; generic "bad app" counts) > `request` (wants a change, reports no failure) > `praise` > `unclear` (meaningless or unrelated text, bare boycott slogans, language not understood).

## Severity (integer 1–5, from the described impact only)
| level | meaning | applied examples |
|---|---|---|
| 1 | no reported problem: praise, neutral/unclear text, pure request | "Good"; "Please add a sleep timer" |
| 2 | dislike, generic criticism, minor annoyance, cosmetic issue | "Worst app ever"; "Too many ads"; "new design is ugly" |
| 3 | degraded or restricted function, some use remains | "only 6 skips unless I pay"; "downloads vanish every week"; "search is bad" |
| 4 | core task clearly blocked | "can't log in"; "crashes every time I open it"; "no song plays" |
| 5 | explicit serious financial, privacy or data harm | "charged twice"; "account hacked"; "all my playlists deleted" |

Stars, angry language and cancellation threats never raise severity on their own.

## Other fields
- **sentiment**: model returns an integer from −2 to 2, and code maps it to `m/2`, giving −1, −0.5, 0, 0.5 or 1.
- **evidence_quote**: produced by code, and always an exact substring of the source. For reviews of 30 words or fewer it is the whole trimmed text. For longer reviews the model copies a 3–10-word anchor and code expands it to the enclosing sentence. If the anchor can't be found, code uses the first sentence and sets `needs_review=true` with reason `quote_anchor_not_found`.
- **entities**: deterministic keyword matches of product features in the text (see `ENTITY_TERMS` in `pipeline/enrich.py`). They are never model-invented.
- **needs_review**: the model flags ambiguous text, missing context or language it can't read, and code adds its own flags.
- **label_config**: `gpt-6-luna+effort-none+enrich-v1+schema-v1`.

## Exported record schema
```json
{"review_id":"…","source_sha256":"…","status":"completed","topic":"playback","intent":"complaint","sentiment":-1.0,
 "severity":4,"entities":["crash"],"evidence_quote":"exact substring","needs_review":false,
 "label_config":"gpt-6-luna+effort-none+enrich-v1+schema-v1","cache_source_id":"<only for exact-text reuse>"}
```
A quarantined record has `{"review_id","source_sha256","status":"quarantined","reason"}`. Empty texts use reason `empty_review_text`.
