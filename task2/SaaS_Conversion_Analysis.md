 # Task 2 — SaaS Conversion Analysis

**Question:** A SaaS platform focused on providing Family Office Intelligence to a targeted audience is only converting 3% of free accounts to paying users. The founders want to increase MRR by improving free-trial to paid conversion. How would you improve this?

---

## Why the generic answers fail

Standard SaaS conversion advice — better onboarding, in-product tours, drip email sequences, gamification, freemium usage caps, sales-assisted trials — will not move this needle meaningfully, because they diagnose the wrong problem. They assume the trial is failing to **demonstrate value**. It isn't. It's failing to **produce an outcome**.

## Who actually buys Family Office intelligence, and what are they hiring it to do?

Not investors researching for their own portfolios. The paying buyers are:

- **Fund GPs raising capital** — need warm paths to LP dollars from family principals.
- **Investment bankers** pitching deals — need to know which single-family offices actively write $5M-$50M direct checks in a given sector.
- **Private-market platforms and syndicate leads** — need contactable decision-makers, not org charts.
- **Wealth managers** prospecting to become the family's outsourced CIO — need to know when a principal is between advisors.
- **Founders raising growth-stage rounds** — need family capital that comes with strategic patience, not just money.

Each of these buyers has a **revenue-attached job**. They are not paying to browse a directory; they are paying to close a specific transaction faster than they could without the tool.

## Why 3% converts

The free tier almost certainly gives them a **list**: names, firms, maybe AUM ranges, filters, exports. The paid tier gives them a **bigger list**, more filters, better exports. This is a data-volume product.

The buyer's job is not to acquire more data. It's to close a deal. A trial that shows "we have more rows than the free tier" does not close deals; it just proves the vendor has a bigger database. The buyer downgrades the value to "reference data I can get elsewhere with more work" and doesn't convert.

The 3% who do convert are almost certainly:
- Users who happened to find a specific contact during trial that closed a specific deal, or
- Users at large institutions where the cost is a rounding error and someone else approves the P.O.

Both segments are conversions we didn't earn — we lucked into them. That's why 3% is a floor, not a ceiling: it converts on accident, not design.

## What to change — in order of expected MRR impact

### 1. Reframe the trial around a closed loop, not a browsable list
The trial should not end with "you've viewed 8 of 10 free contacts, upgrade for unlimited." It should end with a **specific attributable outcome**: *"You reached out to 3 contacts. 1 replied. Here's how paying users get 4× the reply rate."*

That requires the product to observe (or ask for) outreach outcomes. A one-click "did this contact reply?" thumbs-up/down after 7 days. Now the trial is a measurable experiment the buyer ran, not a browsing session. Conversion is now a rational decision on the ROI they just personally witnessed, not a hope.

### 2. Ship one trigger event that only paying users can act on
Family offices are more valuable to reach at **specific moments**: a principal exits a company, a family sells a business, an executive moves between offices, a foundation announces a new mandate, a new investment vehicle files with the SEC. These moments are rare and time-sensitive.

Free tier: **notify** the user that a trigger event occurred at Firm X.
Paid tier: **contact information + warm-intro path** for the decision-maker at Firm X, delivered within 24 hours of the event.

This creates a genuine urgency-to-pay that a bigger-database story never can. The free user sees the trigger fire and knows the window is closing.

### 3. Reprice to align cost with outcome
The current pricing likely charges per seat or per data-volume tier. Both are proxies. The buyer would rather pay per **verified contactable contact they actually reached** or per **closed introduction**. A blended pricing model — a modest platform fee plus a per-successful-connection fee — converts the value conversation from "is this tool worth $X/month?" to "is a warm intro to a family principal worth $Y?" That second question always converts higher, because the market comp for a warm intro is well-known and much higher than a SaaS seat.

### 4. Vet and score contacts, don't just list them
A "verified as reachable in the last 90 days" flag on every contact — with the underlying validation showing (email deliverability, LinkedIn activity, recent press mention) — is what makes the difference between "here's data" and "here's an actionable contact." Charge premium for the verified subset; leave the unverified rows free. Now the free tier is inherently lower value than the paid tier, without any artificial caps.

### 5. Sell to teams, not individuals
Buyers of FO intelligence rarely buy for themselves alone. They buy because a partner asked "who do we know at that family?" during a Monday meeting. A team plan that surfaces "your colleague Sarah reached out to Kathy Lintz at Matter FO last week" turns the product into internal deal-flow infrastructure. Individual-seat pricing under-monetizes this and misses the network effect that would drop churn.

## What NOT to do

- **Do not** add more onboarding — this is not a UX problem.
- **Do not** run more email drips — the buyer's inbox is already the reason they need a better tool.
- **Do not** discount the paid tier — a 3% conversion at $X/month cut to a 5% conversion at $X/2 is a revenue loss, not a gain.
- **Do not** cap the free tier harder — that punishes the user for the vendor's failure to demonstrate incremental value.

## The single question I'd ask before changing anything

Of the 3% who convert today, **what deal did they close in the 30 days before or after signing up?** If the answer is "we don't know," instrument that immediately, because everything above is a hypothesis until you can measure attribution. The founders should be able to state, for the next converted user: "they upgraded because they reached [Person] at [Firm] and it led to [outcome]." Without that, product decisions are guesses.

---

**Summary in one line:** Stop selling a bigger database. Start selling attributable outcomes, verified contactability, and time-sensitive triggers — priced to align with the buyer's revenue job.