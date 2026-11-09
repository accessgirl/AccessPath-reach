# Review policy: every piece of advice gets an independent check

Decided by Heather, Nov 8, 2026.

**This is AccessPath's most important rule.** If the method is ever used for medical necessity or in an injury case, every decision behind it has to be above reproach.

AccessPath takes advice from people who help for free: a nurse checking medical sense, a business coach, family members, contractors. That advice is valuable, and it is still checked before it changes anything.

## The rule

1. **Free advice is verified by a paid, independent professional before it changes a card, a rule, the build or the plan.** Paid, so the check is a professional service with a written result and someone accountable for it, not a favour. Independent, meaning:
   - a fixed fee for the review, agreed before they start, that doesn't depend on what they conclude;
   - no other stake in AccessPath: no shares, no future job or fee riding on the answer;
   - not family, not a friend of the advisor, and not the person who gave the advice;
   - qualified in the area they check (for example, a licensed clinician for medical numbers, a licensed lawyer for legal points).

   Until a paid check is done, the advice is recorded as **unverified** and nothing client-facing relies on it.
2. **Both steps are written down.** Who advised, what they said, who checked it, what the checker concluded, and the dates. Initials are fine where a name shouldn't be public.
3. **A reviewer's opinion is not a source.** A card counts as verified only when five independent published sources agree (see `accesspath/cards.py`). A professional review is recorded separately (the card's `checked_by` field), and it doesn't count toward the five.
4. **Disagreement is kept, not hidden.** If the checker disagrees with the advice, both views are recorded and the decision says which one we followed and why.
5. **No patient information.** Clinical reviewers give general judgement only. Nothing about real patients is sent to us or stored.

## Why

The method behind AccessPath (the cards, the evidence rules, how the reach envelope is built) may later be used by other businesses, by occupational therapists, or as evidence in injury cases. Anything used there has to hold up when an expert challenges it. That needs independent checks, known error ranges and a written trail for every decision. This rule and `docs/build_decisions.md` are that trail.

## Reviewers

| Area | Advisor (unpaid) | Paid independent checker | Status |
|---|---|---|---|
| Medical sense of the cards | J. (RN) | To be named | Package being prepared |
| Business model | Business coach | To be named | Advice recorded Nov 8, 2026 |
| Legal and privacy | | Lawyer (to be hired and paid) | Questions in `docs/privacy.md` |
| Building and renovation | Contractor | To be named | |

Paid checks cost money, so they are batched: advice collects as "unverified" and goes to the checker in one package per area, when there's budget. That keeps the cost down without skipping the check.

## Where things are recorded

- Card changes: the card library's Changelog sheet, plus `checked_by` and `last_checked` on the card.
- Build choices: `docs/build_decisions.md`.
- Business and privacy rules: the doc they change, with the advisor and checker named in the note.
