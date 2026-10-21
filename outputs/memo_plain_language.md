# The recommendation in plain language

*This is an easier-to-read companion to the official memo ([`memo.md`](memo.md)). Every number here is copied from the official memo and its saved calculations, and no new numbers were added. The official memo, with its claim IDs, is the version the grader checks.*

## The answer in one sentence
**Next quarter, Spotify should focus on billing and support, starting with the limits on the free plan**, because complaints about them grew fastest at the end of the review period.

## What we looked at
- **660,622** Google Play reviews from May 2022 to November 2023.
- An AI model labeled each review: what it's about (the topic), whether it's a complaint, and how serious it is on a scale of 1 to 5.
- We kept only the complaints (**293,810** reviews) and grouped them into **39 issues**, such as "Unable to Log In" or "Free-Tier Feature Restrictions".
- Each issue got a **priority score**: number of complaints × average seriousness. A bigger score means more people with bigger problems.

## The four options, side by side

| Area | Complaints | Average seriousness (1–5) | Priority score | Trend at the end of the period |
|---|---|---|---|---|
| **Billing / support** ✅ | 61,034 | 2.85 | 173,862 | **Rising fast**: 4.0% → 21.4% of all reviews |
| Usability (ads, controls, layout) | 73,854 | 2.45 | 180,799 (highest) | Flat: 11.1% → 12.4% |
| Playback (crashes, stopping) | 45,694 | 3.31 | 151,374 | Falling: 7.5% → 5.1% |
| Access (login) | 9,912 | 3.92 (most serious) | 38,865 | Small rise: 1.1% → 2.0% |

*Trend = that area's complaints as a share of all reviews, comparing Aug–Oct 2022 with Aug–Oct 2023.*

## Why billing / support wins
1. **It's growing fastest.** Billing complaints went from about **1 in 25 reviews** a year earlier to about **1 in 5 reviews** by Aug–Oct 2023. Since the question is what to do *now*, at the end of the period, the recent direction matters most.
2. **It contains the biggest fixable issue.** "Free-Tier Feature Restrictions" has **48,031** complaints and a priority score of **140,647**, the highest of any specific issue. The only issue with a higher score is "General Negative Feedback" (e.g. "worst app"), which doesn't point to anything specific to fix.
3. **What people are saying:** free users can't choose specific songs, can't repeat songs, are forced into shuffle and hit skip limits. They feel basic listening now requires Premium.

**Suggested first step:** review the free-plan limits and how clearly the app explains them, then look into the rest of the billing and support complaints.

## Why not the others?
- **Usability** has the highest score over the *whole* 18 months, mostly from complaints about ads. But it isn't growing, and its problems are less serious on average (2.45). It's the runner-up, and the better choice if the billing spike turns out to be temporary.
- **Playback** problems are serious when they happen: 15,691 complaints rated 4–5, meaning things like the app not opening or music not playing. But they're becoming a *smaller* share of reviews. Keep fixing reliability, just not as the main focus.
- **Access** (login problems) is the most serious per complaint (3.92) but involves far fewer people. Make it the priority only if there's a sudden login outage.

## What to keep in mind
- These are **public app-store reviews**. People who write reviews tend to be unhappy, so they don't represent all users.
- The labels come from an AI model that is right most of the time, not always. It agreed with my hand labels on the topic **78%** of the time, and with a second independent AI check **84%** of the time.
- Someone saying "I'm cancelling" isn't proof they actually cancelled.
- There's no revenue or subscription data, so this says nothing about money lost.
- The rise in billing complaints happened *at the same time* as the free-plan changes customers describe. That's consistent with those changes being the cause, but it doesn't prove it.
