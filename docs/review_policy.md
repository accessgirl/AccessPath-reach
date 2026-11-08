# Review policy: every piece of advice gets an independent check

Decided by Heather, Nov 8, 2026.

AccessPath takes advice from people who help for free: a nurse checking medical sense, a business coach, family members, contractors. That advice is valuable, and it is still checked before it changes anything.

## The rule

1. **Advice is checked by an unbiased third party before it changes a card, a rule, the build or the plan.** The checker has no stake in AccessPath: not paid by it, not family, not the person who gave the advice.
2. **Both steps are written down.** Who advised, what they said, who checked it, what the checker concluded, and the dates. Initials are fine where a name shouldn't be public.
3. **A reviewer's opinion is not a source.** A card counts as verified only when five independent published sources agree (see `accesspath/cards.py`). A professional review is recorded separately (the card's `checked_by` field), and it doesn't count toward the five.
4. **Disagreement is kept, not hidden.** If the checker disagrees with the advice, both views are recorded and the decision says which one we followed and why.
5. **No patient information.** Clinical reviewers give general judgement only. Nothing about real patients is sent to us or stored.

## Why

The method behind AccessPath (the cards, the evidence rules, how the reach envelope is built) may later be used by other businesses, by occupational therapists, or as evidence in injury cases. Anything used there has to hold up when an expert challenges it. That needs independent checks, known error ranges and a written trail for every decision. This rule and `docs/build_decisions.md` are that trail.

## Reviewers

| Area | Advisor (unpaid) | Independent checker | Status |
|---|---|---|---|
| Medical sense of the cards | J. (RN) | To be named | Package being prepared |
| Business model | Business coach | To be named | Advice recorded Nov 8, 2026 |
| Legal and privacy | | Lawyer (to be hired) | Questions in `docs/privacy.md` |
| Building and renovation | Contractor | To be named | |

## Where things are recorded

- Card changes: the card library's Changelog sheet, plus `checked_by` and `last_checked` on the card.
- Build choices: `docs/build_decisions.md`.
- Business and privacy rules: the doc they change, with the advisor and checker named in the note.
