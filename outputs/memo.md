## The answer in one sentence

**Next quarter, Spotify should focus on billing and support, starting with the limits on the free plan, because complaints about them grew fastest at the end of the review period.**

## What we looked at

- **660,622** Google Play reviews from May 2022 to November 2023 [A2c]. An AI model labeled **660,555** of them [A1]: what each review is about, whether it is a complaint, and how serious it is on a scale of 1 to 5.
- We kept the complaints, **293,810** reviews [A2], and grouped them into **39** issues [A2b], such as "Unable to Log In" or "Free-Tier Feature Restrictions".
- Each issue gets a **priority score**: number of complaints × average seriousness. A bigger score means more people with bigger problems.

## The four options, side by side

| Area | Complaints | Average seriousness (1–5) | Priority score | Share of all reviews, Aug–Oct 2022 → Aug–Oct 2023 |
|---|---:|---:|---:|---|
| **Billing / support** ✅ | 61,034 [A36] | 2.85 [A39] | 173,862 [A38] | **4.0% [A16] → 21.4% [A25]**, rising fast |
| Usability (ads, controls, layout) | 73,854 [A30] | 2.45 [A33] | 180,799 [A32], the highest | 11.1% [A14] → 12.4% [A23], flat |
| Playback (crashes, music stopping) | 45,694 [A48] | 3.31 [A51] | 151,374 [A50] | 7.5% [A12] → 5.1% [A21], falling |
| Access (login) | 9,912 [A60] | 3.92 [A63], the most serious | 38,865 [A62] | 1.1% [A18] → 2.0% [A27], small rise |

Trend shares compare all classified reviews in each period: 85,236 in Aug–Oct 2022 [A11] and 161,173 in Aug–Oct 2023 [A20]. November 2023 is left out because it is a partial month [A29].

## Why billing / support wins

1. **It is growing fastest.** Billing and support complaints went from 4.0% of reviews [A16] a year earlier to 21.4% of reviews [A25] by Aug–Oct 2023. The question is what to do *now*, at the end of the period, so the recent direction matters most. Over the whole period usability's score of 180,799 [A32] is slightly higher than billing/support's 173,862 [A38], but usability is not growing.
2. **It contains the biggest fixable issue.** `ISS-billing-free_tier_restrictions` (Free-Tier Feature Restrictions) has 48,031 complaints [C004], an average seriousness of 2.93 [C005] and a priority score of 140,647 [C006]. The only issue with a higher score is `ISS-other-general_negative` (General Negative Feedback, e.g. "worst app") at 157,846 [C003], which does not point to anything specific to fix.
3. **What customers are saying.** Free users say they can no longer choose songs, repeat songs or avoid shuffle, and that basic listening now requires Premium (`84300454-6a70-40f5-89bc-f9818dd4076d`, `cba5ab8b-0bbb-45b8-8925-b6d843d12d42`).

**Suggested first step:** review the free-plan limits and how clearly the app explains them, then look into the rest of the billing and support complaints.

## Why not the others?

- **Usability** has the highest score over the whole period, 180,799 [A32], driven by `ISS-usability-ads_interruptions` (Frequent Ad Interruptions) with 36,257 complaints [C007] and a priority score of 77,273 [C009]. But its share of reviews barely moved, 11.1% [A14] to 12.4% [A23], and its problems are milder on average, 2.45 [A33]. It is the runner-up, and the better choice if the billing spike turns out to be temporary.
- **Playback** problems are serious when they happen: 15,691 complaints were rated 4 or 5 [A52], such as the app not opening or music not playing. The top playback issue, `ISS-playback-playback_stops_or_skips` (Playback Stops or Skips), has a priority score of 37,795 [C015]. But playback is a shrinking share of reviews, 7.5% [A12] to 5.1% [A21]. Keep fixing reliability, just not as the main focus.
- **Access** (login) is the most serious per complaint, 3.92 [A63], but involves far fewer people, 9,912 complaints [A60]. `ISS-access-login_failure` (Unable to Log In) has a priority score of 28,532 [C018]. Make it the priority only if there is a sudden login outage.

## Evidence (example reviews)

- `84300454-6a70-40f5-89bc-f9818dd4076d`: says the app used to be good, but now everything needs Premium.
- `cba5ab8b-0bbb-45b8-8925-b6d843d12d42`: describes losing the ability to pick songs and repeat them unless they pay.
- `188599a2-694a-4a3a-9c38-ea94f2d12cae`: music stops playing after an ad ends.
- `c30e8e8f-0790-4d25-b6a1-8f451285dc95`: music will not play even after reinstalling the app.
- `47a1557c-36e8-4e7a-9b72-0a940c2ec715`: cannot log in with a phone number after many tries.

## What to keep in mind

- These are **public app-store reviews**. People who write reviews tend to be unhappy, so they do not represent all users.
- The labels come from an AI model that is usually, but not always, right. It agreed with hand labels on the topic 78.0% of the time [A8], and with a second, independent AI check 84.1% of the time [A5].
- Someone saying "I'm cancelling" is not proof they actually cancelled.
- There is no revenue or subscription data, so this says nothing about money lost.
- The rise in billing complaints happened *at the same time* as the free-plan changes customers describe. That is consistent with those changes being the cause, but it does not prove it.
- 67 reviews could not be classified, including empty ones [A3].

*How this memo was made: the pipeline's memo role (AI, prompt `memo-v3`) wrote [`memo_v3.md`](memo_v3.md) from saved numbers only. A person then rewrote it in plain language, keeping the conclusion, every number and every citation. The same code checks were rerun on this text: every citation exists, every number matches a saved value, and every review ID is from the evidence pack. Results are in `memo_validation.json`. The dashboard shows the original AI-generated text.*
