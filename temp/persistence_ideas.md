# STEP Metadata Persistence — Brainstorm

## The Problem
SolidWorks (and Fusion 360) rebuild STEP files from scratch on re-export.
They only preserve **geometry** and **part names**. Everything else is destroyed.

## What We've Tried (and failed)

| # | Technique | Result |
|---|-----------|--------|
| 1 | `/* comment block */` with JSON | Stripped — comments aren't data |
| 2 | `PROPERTY_DEFINITION` → `PRODUCT_DEFINITION_SHAPE` | Stripped — SW doesn't import shape-level properties |
| 3 | `PROPERTY_DEFINITION` → `PRODUCT_DEFINITION` (SW's own pattern) | Stripped — SW doesn't import foreign properties at all |
| 4 | `PRODUCT` description field with `[SVFM:base64]` | Stripped — SW rewrites the PRODUCT entity |
| 5 | `DESCRIPTIVE_REPRESENTATION_ITEM` with base64 payload | Stripped |

## What DOES Survive SolidWorks Round-Trip

1. **B-Rep geometry** — exact surfaces, curves, edges, vertices, topology
2. **Part name** (PRODUCT name → filename) — but just a short string
3. **Assembly structure** — component relationships
4. That's it.

---

## New Ideas — Ranked by Feasibility

### TIER 1: Encode into geometry itself

**Idea 6: Micro-feature encoding**
Add an infinitesimally small construction point or wire body at a known location.
The coordinates of the point encode data (each decimal place is a data channel).
- Pro: Geometry always survives
- Con: Corrupts the model, might cause manufacturing issues, insane

**Idea 7: Vertex coordinate steganography**
Slightly perturb existing vertex positions by nanometer-scale amounts to encode bits.
E.g., if vertex X = 10.000000, shift to 10.000001 to encode a "1" bit.
- Pro: Invisible to machining (sub-nanometer changes)
- Con: CAD kernels may re-parameterize surfaces and snap coordinates, destroying the encoding. STEP uses finite precision. Extremely fragile.

**Idea 8: Extra edge/wire body as data carrier**
Add a B-spline curve inside the solid whose control points spell out the data.
Mark it as construction geometry (not manufacturing-relevant).
- Pro: Survives any tool that preserves geometry
- Con: Still corrupts the model. Extra edges show up in feature tree.

### TIER 2: Encode into the part name

**Idea 9: Part name suffix encoding**
Append a hash/short code to the part name: `MyPart__SV_a3f8b2`
The hash maps to a server-side or local database of metadata.
- Pro: Part names DO survive SolidWorks
- Con: Requires external lookup (database/API). Name gets ugly. User might rename.

**Idea 10: Part name as full payload**
Encode the entire metadata as base64 in the part name:
`MyPart__SVFM_eyJmYWNlX21ldGE...`
- Pro: Self-contained, no external storage
- Con: Part names have length limits. SW might truncate. Very ugly in feature tree.

### TIER 3: Exploit STEP entities SW might preserve

**Idea 11: DRAUGHTING_MODEL / 3D Annotation**
SW supports AP242 MBD (Model-Based Definition). If we write thread callouts as
proper AP242 `DRAUGHTING_CALLOUT` / `GEOMETRIC_TOLERANCE` entities, SW's MBD
import might preserve them.
- Pro: This is the "correct" way to store thread data in STEP
- Con: Extremely complex to implement. AP242 PMI entity chains are 50+ entities deep.
  OCC has partial AP242 write support but it's poorly documented.

**Idea 12: REPRESENTATION_MAP / MAPPED_ITEM abuse**
Create a dummy MAPPED_ITEM that references a REPRESENTATION containing our data
as DESCRIPTIVE_REPRESENTATION_ITEMs. If SW treats it as a geometric mapping,
it might preserve it.
- Pro: Uses geometric-level entities
- Con: Likely causes import errors or gets stripped as invalid geometry

**Idea 13: LAYER assignment with encoded name**
STEP layers (`PRESENTATION_LAYER_ASSIGNMENT`) have a name field. Assign faces
to layers with names like `SVFM_face0_M10x1.5_6g`. SW imports layers.
- Pro: Layers sometimes survive. Layer names are free text.
- Con: SW might not preserve layer assignments from STEP. Layer names have limits.
  Need to verify if SW reads PRESENTATION_LAYER_ASSIGNMENT.

**Idea 14: COLOR encoding (steganography)**
Encode metadata into the least-significant bits of face colors.
E.g., #FF0000 (red) → #FF0001 (encode 1 bit in blue channel).
Use a lookup table of colors where each color encodes a thread specification.
- Pro: Colors sometimes survive through SW (body-level)
- Con: Face-level colors get stripped by SW. Even body-level colors may be reassigned.
  Very limited bandwidth. Fragile.

### TIER 4: Hybrid approaches

**Idea 15: Geometry fingerprinting + embedded hash**
Compute a SHA256 of each face's geometry (centroid, area, surface type).
Store a short hash in the part name suffix: `MyPart__SV_a3f8b2`
On our server/app, maintain a database mapping hash → full metadata.
When reimporting after SW round-trip, recompute fingerprints and match.
The part name hash confirms which project the file belongs to.
- Pro: Works with any tool. Fingerprints are deterministic.
- Con: Requires local database (but it's app-managed, not a sidecar file per se)

**Idea 16: Encode in file HEADER timestamps**
STEP header has: `FILE_NAME('name','2024-01-01T12:00:00',...)` 
The timestamp/author fields are free text. Encode data there.
- Pro: Simple text manipulation
- Con: SW rewrites the header completely. Dead on arrival.

**Idea 17: Encode in PRODUCT_DEFINITION_FORMATION description**
`PRODUCT_DEFINITION_FORMATION('version_id','description',#PRODUCT)`
The description field might survive if SW maps it to a configuration description.
- Pro: Part of the product chain SW reads
- Con: Probably still gets rewritten. Untested.

### TIER 5: Outside-the-box

**Idea 18: ZIP container (.svproj)**
Don't export a .step file. Export a .svproj which is a ZIP containing:
- model.step (the actual STEP)
- metadata.json (face fingerprints → metadata)
User always works with .svproj files. When they need to send to SW, they
extract the .step. When they get it back from SW, they re-import into .svproj
which auto-matches metadata by fingerprint.
- Pro: Clean, professional (like .f3d, .3mf, .docx)
- Con: User called this a "sidecar" and rejected it

**Idea 19: STEP-embedded ZIP (polyglot file)**
A file that is BOTH a valid STEP file AND a valid ZIP file.
ZIP format reads from the end of file. STEP reads from the start.
Append a ZIP archive containing metadata.json after END-ISO-10303-21;
- Pro: Single file. Opens in CAD as STEP. Our tool reads the ZIP trailer.
- Con: SW will strip everything after END-ISO-10303-21 on re-export.

**Idea 20: QR code in a face texture/annotation**
Encode metadata as a QR code embedded as a DRAUGHTING entity or surface texture.
- Pro: Creative
- Con: Absurd. SW won't preserve it.

---

## Honest Assessment

**Nothing embedded in a STEP file survives a SolidWorks re-export.**
SolidWorks uses a parasolid kernel that builds its own B-rep from the imported
geometry, then writes a completely new STEP file. It doesn't carry forward
ANY entities from the original file.

The only data channels that survive are:
- Face geometry (centroid, area, normals, surface type, bounding box)
- Part name (short string)

The most practical approach that doesn't use a separate file:
- **Idea 15**: Part name hash + app-managed database with geometry fingerprinting
- Or **Idea 10**: Encode payload directly in part name (ugly but self-contained)
