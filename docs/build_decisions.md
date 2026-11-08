# Build decisions and where they came from

Every choice in how the 3D body and the reach engine are built, the source behind it, and what we took from that source. This is the record a professional builder or reviewer can follow without anyone walking them through it.

Papers themselves live in Google Drive, never in this repo:

- **Build references - 3D human models / Used in the build**: papers a decision below rests on.
- **Build references - 3D human models / Parked - for future use**: papers read and kept, but not used yet. Each gets a one-line note in the parked list at the bottom saying why.
- **Eyes only - sources not cleared for commercial use**: papers whose licence doesn't allow commercial use. We cite their numbers only.

## How to add a row

One row per decision: what we decided, the source (authors, year, journal or report), what exactly we took from it (a number, a method, a warning), what we chose *not* to take and why, and the date. If two sources disagree, list both and say which one we followed.

## Decisions so far

| Decision | Source | What we took | Not taken / why | Date |
|---|---|---|---|---|
| Split a measured arm length into upper arm, forearm and hand | Drillis & Contini 1966 segment ratios (via Winter, *Biomechanics and Motor Control of Human Movement*) | Ratios 0.186 / 0.146 / 0.108 of height, used as proportions of the measured arm | Using the ratios against height when the arm is measured: the measurement wins | Nov 2026 |
| Seated wheelchair-user body sizes when nothing is measured | Paquet & Feathers 2004, *Ergonomics* (eyes only) | Acromion height, overall breadth, knee height ranges | Full tables stay in Drive | Nov 2026 |
| Check reach results against real wheelchair users | IDeA Center Design Resource #20, University at Buffalo | Share of measured users who could reach each height | Chart images | Nov 2026 |
| Knee space under sinks and counters | 2010 ADA Standards, 306.3 | 27 in (0.685 m) minimum knee clearance | | Nov 2026 |
| Trunk counts separately from height | AccessPath demo (two bodies, same height, trunk 23.5 vs 20 in) | Engine shows 8 cm difference in top reach, so trunk is measured, not estimated | | Nov 2026 |

## Parked papers

| Paper | Why it's parked | Could matter for |
|---|---|---|
| | | |
