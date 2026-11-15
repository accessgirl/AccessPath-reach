# Components and licences

Every piece of software and data AccessPath uses, its licence, and whether that licence allows commercial use, changes and hosting. "Free" or "open source" doesn't settle that, so each line names the licence itself.

Checked Nov 8, 2026 by Claude (build chat), from each package's own licence file or PyPI record. **A lawyer still needs to review this before AccessPath is sold or hosted** (see the lawyer questions in docs/privacy.md).

## Software the engine needs (`pip install -e .`)

| Component | Version checked | Licence | Commercial use | Changes | Hosting | Notes |
|---|---|---|---|---|---|---|
| ikpy (reach chain) | 4.4.4 | Apache-2.0 (repository LICENSE) | Yes | Yes | Yes | Keep its licence and notice file with any copy we ship |
| numpy | 1.26.4 installed | BSD-3-Clause (plus small parts under 0BSD, MIT, Zlib, CC0) | Yes | Yes | Yes | |
| scipy | 1.17.1 installed | BSD-3-Clause | Yes | Yes | Yes | |
| openpyxl (reads the card library) | 3.1.5 | MIT | Yes | Yes | Yes | |

## Only for tests, the Blender view and the video

| Component | Version checked | Licence | Commercial use | Changes | Hosting | Notes |
|---|---|---|---|---|---|---|
| pytest | 9.2.0 | MIT | Yes | Yes | Yes | Tests only |
| Blender / bpy | 5.0.1 installed | GPL-3.0 | Yes | Yes, but changes we *distribute* must be shared under GPL | Yes | Only `blender/` and `video/` import it; the engine (`accesspath/`) doesn't. Pictures and videos Blender renders are ours. Shipping our Blender scripts to customers would put those scripts under GPL: ask the lawyer before doing that |
| Pillow | 10.2.0 installed | MIT-CMU | Yes | Yes | Yes | Video frames |
| matplotlib | (video only) | Matplotlib licence (PSF-based) | Yes | Yes | Yes | |
| imageio-ffmpeg | 0.8.1 on PyPI | BSD-2-Clause | Yes | Yes | Yes | It bundles an ffmpeg program, which has its own (LGPL or GPL) licence. Fine for making our own videos; check before shipping it |
| kokoro-onnx (narration voice) | 0.6.1 on PyPI | MIT (repository LICENSE) | Yes | Yes | Yes | |
| Kokoro-82M voice model | | Apache-2.0 (model card) | Yes | Yes | Yes | |
| soundfile | 0.14.0 on PyPI | BSD-3-Clause | Yes | Yes | Yes | |

## Planned, not used yet

| Component | Licence | Commercial use | Watch out for |
|---|---|---|---|
| ezdxf (reading AutoCAD DXF drawings) | MIT | Yes | |
| MakeHuman (body models) | Program: AGPL-3.0. Bundled assets: CC0 | Program: yes, but AGPL means a *modified* MakeHuman offered to users over a network must have its changes published. Assets: yes, no conditions | Use the CC0 assets; keep any changed MakeHuman code off a hosted service until the lawyer has looked. Community add-ons carry their own licences: check each one |
| ADA CAD block libraries | Varies by library | Only libraries with explicit commercial terms | None in use. Anything with unclear terms stays out until confirmed |

## Data

| Data | Where it's used | Terms | Notes |
|---|---|---|---|
| Card library numbers | `data/card_library.xlsx` | Per card: see the `access_license` column | Numbers are cited as facts; no text or figures from papers are copied. `python -m accesspath check-cards` lists cards from non-commercial or subscription papers |
| IDeA Center Design Resource #20 | `data/idea_reach.json` | Public PDF from the University at Buffalo; no licence stated | Chart percentages copied as facts, with citation. The charts themselves aren't reproduced |
| Paquet & Feathers 2004 | `data/wheelchair_size.json` | Subscription journal (Elsevier) | A few numbers only, with citation; the tables stay in Drive |
| CDC/NCHS anthropometric reference data | Body Bands sheet | U.S. government work, public domain | |
| ADA 2010 Standards | Door and knee-space rules | U.S. government, public | |

## How to add a component

Add a row before the code that uses it is merged: name, version, where it came from, licence and a link to its text, whether commercial use, changes and hosting are allowed, the date checked and who checked it. Anything with unclear terms is left out until it's confirmed.
