# Geometry Hash + SQLite Metadata Store — Implementation Plan

## Concept
Every face has a unique geometric signature that doesn't change through any
CAD tool round-trip. We compute a deterministic hash from each face's geometry
and use it as a key in a SQLite database. When a STEP file is loaded — even
after being rewritten by SolidWorks — we fingerprint every face, look up the
hashes in the DB, and restore all metadata automatically.

## Face Fingerprint Design

The hash must be **deterministic** (same face → same hash always) and
**collision-resistant** (different faces → different hashes).

Inputs to the hash (all from OCC geometry, not tessellation):
```
1. Surface type enum     (Plane, Cylinder, Cone, Sphere, Torus, BSpline, etc.)
2. Face centroid         (center of mass via BRepGProp, rounded to 6 decimals)
3. Face area             (surface area via BRepGProp, rounded to 6 decimals)
4. Bounding box          (Xmin,Ymin,Zmin,Xmax,Ymax,Zmax rounded to 6 decimals)
5. Surface normal at centroid  (direction vector, rounded to 4 decimals)
6. Number of edges       (integer — topological edge count)
7. Number of vertices    (integer — topological vertex count)
```

Concatenate all values into a canonical string, then SHA256 → 16-char hex.

### Why this works:
- Surface type: plane vs cylinder vs cone is invariant
- Centroid: center of mass is pure geometry, doesn't depend on face ordering or entity IDs
- Area: computed from the surface, not tessellation
- Bounding box: tight box around the face
- Normal: orientation of the surface
- Edge/vertex counts: topological invariant

### Why 6 decimal places:
- STEP files use ~15 significant digits, but CAD kernels may re-parameterize
  surfaces slightly. 6 decimals (micrometer precision for mm parts) is stable
  enough to survive kernel differences while still being unique.

## Database Schema

```sql
-- Metadata keyed by face geometry hash
CREATE TABLE face_meta (
    face_hash   TEXT NOT NULL,      -- SHA256-based fingerprint (16 hex chars)
    meta_json   TEXT NOT NULL,      -- JSON blob: {"thread": {...}, "tolerance": {...}, ...}
    updated_at  TEXT NOT NULL,      -- ISO timestamp
    PRIMARY KEY (face_hash)
);

-- Optional: track which STEP files we've seen (for UI/history)
CREATE TABLE models (
    model_hash  TEXT NOT NULL,      -- hash of all face hashes sorted (model fingerprint)
    filename    TEXT,
    face_count  INTEGER,
    last_opened TEXT NOT NULL,
    PRIMARY KEY (model_hash)
);
```

## Flow

### On Upload / Load:
1. Parse STEP with OCC (existing flow)
2. For each face: compute fingerprint hash using BRepGProp
3. Query SQLite: `SELECT meta_json FROM face_meta WHERE face_hash IN (?,...)`
4. Merge: any face whose hash has a DB entry gets its metadata restored
5. Also try embedded STEP metadata (existing 3-layer extraction) as fallback
6. Return face data to frontend with restored metadata
7. Log to console: "Restored metadata for N faces from geometry DB"

### On Set Thread / Set Color:
1. Existing flow: update in-memory model.face_meta
2. NEW: also write to SQLite keyed by face hash
3. This happens on every /set_thread and /set_color call

### On Export:
1. Existing flow: write STEP with embedded metadata (entities + description + comment)
2. No change needed — the STEP still carries embedded data for tools that preserve it
3. The SQLite DB is the SolidWorks-proof backup

### On Re-import After SolidWorks:
1. Upload the SolidWorks-exported STEP (no embedded metadata)
2. Fingerprint all faces
3. SQLite lookup finds matches → metadata restored automatically
4. User sees their thread callouts right where they left them

## File Structure
```
c:\repo_cad\
  app.py
  stepviewer.db          ← SQLite database (auto-created)
  ...
```

## Implementation Steps

1. Add `face_fingerprint()` function using BRepGProp + BRepAdaptor
2. Add SQLite helper module (init, save, lookup)
3. Compute fingerprints during `load_step_xcaf()` — store on model state
4. On `/set_thread` and `/set_color`: persist to SQLite by face hash
5. On load: after OCC parsing, query SQLite for known face hashes
6. Merge DB metadata with any embedded STEP metadata (embedded wins if both exist)
7. Return merged metadata to frontend
8. Add roundtrip test: load → set thread → export → strip all metadata → reimport → verify DB restore

## Edge Cases
- **Face hash collision**: Extremely unlikely with SHA256, but if two faces have
  identical geometry (e.g., symmetric holes), they'd share a hash. This is actually
  CORRECT behavior — identical geometry should have identical metadata.
- **Slightly modified geometry**: If the user modifies the part in SolidWorks
  (e.g., changes a hole diameter), the fingerprint changes and old metadata
  won't match. This is correct — the face is genuinely different now.
- **Multiple parts with same face geometry**: Different parts might have faces
  with the same centroid/area/etc. The hash includes enough dimensions (7 inputs)
  to make this extremely unlikely.
