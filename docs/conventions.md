# Conventions: how the verifier's words and numbers map to the standards

The verifier has to hand data to other software (Blender now; possibly OpenSim, motion capture, CAD or clinical records later). This page pins down what each name, axis and angle means, in the terms of two published standards, so nothing gets misread in transfer.

- **Movement:** ISB joint coordinate standard. Wu G. et al. (2005), *ISB recommendation on definitions of joint coordinate systems of various joints for the reporting of human joint motion, Part II: shoulder, elbow, wrist and hand.* J Biomech 38:981–992. Hip, knee, ankle and spine are in Part I (Wu et al. 2002, J Biomech 35:543–548), which isn't in the project files yet.
- **The person:** ISNCSCI, the International Standards for Neurological Classification of Spinal Cord Injury (ASIA/ISCoS worksheet, rev 04/2026; Rupp et al. 2026, doi:10.46292/sci26-00067).

The PDFs themselves are not in the repo, because they are under copyright. The terms and numbers taken from them are in `data/card_library.xlsx` (`ISB_term` column) and `data/isncsci.json`.

## 1. Axes and units

| | Verifier and Blender | ISB and OpenSim |
|---|---|---|
| Forward | +y | +X |
| Up | +z | +Y |
| Right | +x | +Z |
| Units | metres, degrees | metres, degrees |

Both frames are right-handed, so converting between them only relabels the axes: ISB (X, Y, Z) = verifier (y, z, x). `accesspath.isb.to_isb()` and `from_isb()` do this. Use them on `.ply` envelopes and fixture positions before loading them into ISB-based software.

The verifier's origin is on the floor under the hip centre. ISB puts the thorax origin at the sternal notch (IJ), so positions also need that offset when a tool expects thorax-relative data.

## 2. Joint names

| Card `joint_id` | ISB joint (distal segment relative to proximal) | Standard |
|---|---|---|
| `trunk` | Thorax relative to pelvis | Part I (spine); Part II §2.4.1 gives thorax vs. global |
| `shoulder_R/L` | Humerus relative to thorax (thoracohumeral) | Part II §2.4.7 |
| `elbow_R/L` | Forearm relative to humerus | Part II §3.4.1 |
| `wrist_R/L` | Third metacarpal relative to radius (radiocarpal) | Part II §4.4.1 |
| `hand_*` | Metacarpophalangeal and interphalangeal joints | Part II §4.4.1 |
| `hip_R/L` | Femur relative to pelvis | Part I |
| `knee_R/L` | Tibia relative to femur | Grood & Suntay 1983, as used by ISB |
| `ankle_R/L` | Calcaneus relative to tibia | Part I |

`_affected` in a condition card is our own shorthand for "the side the profile names". It turns into `_R` or `_L` before any angle is used.

## 3. Angles and signs

**The cards always store degrees from neutral as positive numbers, one direction per row.** ISB instead gives each rotation a sign. When passing card numbers to an ISB tool, apply the sign below.

| Card motion | ISB angle | ISB sign |
|---|---|---|
| Shoulder flexion | Elevation, in plane of elevation 90° | Elevation is a **negative** rotation about the humerus X axis; the clinical angle is reported positive |
| Shoulder abduction | Elevation, in plane of elevation 0° | Same as above |
| Shoulder extension | Elevation behind the body (plane of elevation about −90°) | Same as above |
| Shoulder internal / external rotation (no cards yet) | Axial rotation | Internal +, external − |
| Elbow flexion | α about humerus Z | Flexion +, hyperextension − |
| Forearm pronation / supination (no cards yet) | γ about forearm Y | Pronation +, supination − |
| Wrist flexion / extension | α about radius Z | Flexion +, extension − |
| Wrist radial / ulnar deviation (no cards yet) | β | Ulnar +, radial − |
| Trunk flexion / extension | α about Z | Flexion −, extension + (Part II §2.4.1) |
| Trunk lateral flexion (card: trunk abduction) | β about X | Right +, left − |

ISB mirrors the left arm's axes, so flexion, pronation and ulnar deviation are positive on both sides. That matches the cards, which use the same numbers for R and L.

### The shoulder's rotation order

ISB describes the shoulder with three angles applied in Y‑X‑Y order:
1. **Plane of elevation:** which way the arm is raised. 0° is out to the side, 90° is straight forward.
2. **Elevation:** how far it is raised. 0° is hanging, 90° is horizontal.
3. **Axial rotation:** how far it is turned about its own long axis.

The verifier's rig and reach chain instead use flexion followed by abduction (`blender/rig.py`, `accesspath/kinematics.py`). The two agree for pure flexion and for pure abduction. For combined poses, `accesspath.isb.shoulder_elevation(arm_dir, side)` gives the ISB numbers from the upper-arm direction.

When a source reports shoulder range in ISB terms (for example "maximum elevation 150° in the scapular plane"), enter it on the card closest to its plane of elevation. Say in `notes` which plane it was measured in.

## 4. Spinal cord injury profiles (ISNCSCI)

Name spinal cord injury profiles the way a clinical exam writes them:

```
SCI_<neurological level>_AIS_<grade>[_anything]
e.g.  SCI_C6_AIS_A    SCI_T10_AIS_C_wheelchair
```

- **Level:** one of C1–C8, T1–T12, L1–L5, S1–S3, S4-5.
- **AIS grade:** A to E, as defined in `data/isncsci.json`.

`check-cards` rejects a profile starting with `SCI` that doesn't follow this pattern. `accesspath.isncsci.parse_sci_name()` reads a name back into level and grade.

The key muscles the exam tests show which cards a level affects (`key_muscles_below(level)`):

| Level | Key muscle | Card joint and motion |
|---|---|---|
| C5 | Elbow flexors | elbow flexion |
| C6 | Wrist extensors | wrist extension |
| C7 | Elbow extensors | elbow extension |
| C8 | Finger flexors | hand grip / finger flexion |
| T1 | Finger abductors (little finger) | hand (no card yet) |
| L2 | Hip flexors | hip flexion |
| L3 | Knee extensors | knee extension (no card yet) |
| L4 | Ankle dorsiflexors | ankle dorsiflexion |
| L5 | Long toe extensors | toe (no card yet) |
| S1 | Ankle plantar flexors | ankle plantarflexion |

ISNCSCI grades **strength (0–5)**, not range of motion. A C6 AIS A person usually has full passive elbow extension range but can't hold the arm up against gravity without triceps. So an SCI profile's cards need sourced functional-reach or active-range data per level. The standard gives the vocabulary and says which joints to look at; it doesn't supply the numbers. No SCI profiles exist yet for this reason.
