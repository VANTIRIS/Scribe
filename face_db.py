"""
Geometry-based face metadata database.

Each face gets a fingerprint from its geometry (surface type, centroid, area,
bounding box dimensions, edge/vertex counts).  Metadata is stored in SQLite.

Matching uses TWO strategies:
  1. Exact hash match (fast, covers same-kernel round-trips)
  2. Fuzzy match with tolerance (covers cross-kernel round-trips like SolidWorks)
     Topology must match exactly (surface type, edge count, vertex count).
     Continuous values (centroid, area, dimensions) use configurable tolerance.
"""

import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timezone

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer

# ── Config ───────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stepviewer.db")

# Tolerance for fuzzy matching (absolute, in model units — typically mm)
FUZZY_TOL_POSITION = 0.01      # centroid: 10 microns
FUZZY_TOL_AREA     = 0.1       # area: 0.1 mm^2
FUZZY_TOL_DIM      = 0.01      # bbox dimensions: 10 microns


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create/migrate tables."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS face_meta (
            face_hash   TEXT PRIMARY KEY,
            meta_json   TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            -- Raw fingerprint values for fuzzy matching
            surf_type   INTEGER,
            cx          REAL,
            cy          REAL,
            cz          REAL,
            area        REAL,
            dx          REAL,
            dy          REAL,
            dz          REAL,
            n_edges     INTEGER,
            n_verts     INTEGER
        );

        -- Index for fuzzy lookups (filter by topology first, then range-check numerics)
        CREATE INDEX IF NOT EXISTS idx_face_topo
            ON face_meta (surf_type, n_edges, n_verts);
    """)
    conn.close()


# ── Face fingerprinting ─────────────────────────────────────────────────────

def _norm(val):
    """Normalize -0.0 to 0.0 for consistent hashing."""
    return val + 0.0


def face_fingerprint_raw(face) -> dict:
    """
    Compute raw fingerprint values for a TopoDS_Face.
    Returns a dict with all the numeric components.
    """
    # Surface type
    surf = BRepAdaptor_Surface(face)
    surf_type = int(surf.GetType())

    # Area + centroid
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    area = _norm(props.Mass())
    cm = props.CentreOfMass()
    cx, cy, cz = _norm(cm.X()), _norm(cm.Y()), _norm(cm.Z())

    # Bounding box dimensions (sorted, orientation-independent)
    bbox = Bnd_Box()
    BRepBndLib.Add_s(face, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dims = sorted([
        _norm(abs(xmax - xmin)),
        _norm(abs(ymax - ymin)),
        _norm(abs(zmax - zmin)),
    ])

    # Topology counts
    n_edges = 0
    exp_e = TopExp_Explorer(face, TopAbs_EDGE)
    while exp_e.More():
        n_edges += 1
        exp_e.Next()

    n_verts = 0
    exp_v = TopExp_Explorer(face, TopAbs_VERTEX)
    while exp_v.More():
        n_verts += 1
        exp_v.Next()

    return {
        "surf_type": surf_type,
        "cx": cx, "cy": cy, "cz": cz,
        "area": area,
        "dx": dims[0], "dy": dims[1], "dz": dims[2],
        "n_edges": n_edges, "n_verts": n_verts,
    }


def face_fingerprint(face) -> str:
    """
    Compute a 16-char hex hash from face geometry.
    Uses 3-decimal rounding for the hash (exact match within same kernel).
    """
    raw = face_fingerprint_raw(face)
    canonical = (
        f"T{raw['surf_type']}|"
        f"C{round(raw['cx'],3)},{round(raw['cy'],3)},{round(raw['cz'],3)}|"
        f"A{round(raw['area'],3)}|"
        f"D{round(raw['dx'],3)},{round(raw['dy'],3)},{round(raw['dz'],3)}|"
        f"E{raw['n_edges']}V{raw['n_verts']}"
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ── Database operations ──────────────────────────────────────────────────────

def save_face_meta(face_hash: str, meta: dict, raw: dict = None):
    """Upsert metadata + raw fingerprint values for a face hash."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    if raw:
        conn.execute(
            """INSERT OR REPLACE INTO face_meta
               (face_hash, meta_json, updated_at,
                surf_type, cx, cy, cz, area, dx, dy, dz, n_edges, n_verts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (face_hash, json.dumps(meta), now,
             raw["surf_type"], raw["cx"], raw["cy"], raw["cz"], raw["area"],
             raw["dx"], raw["dy"], raw["dz"], raw["n_edges"], raw["n_verts"]),
        )
    else:
        conn.execute(
            "INSERT OR REPLACE INTO face_meta (face_hash, meta_json, updated_at) VALUES (?,?,?)",
            (face_hash, json.dumps(meta), now),
        )
    conn.commit()
    conn.close()


def lookup_face_meta(face_hashes: list[str]) -> dict[str, dict]:
    """
    Exact hash lookup — fast path for same-kernel round-trips.
    Returns {hash: meta_dict} for hashes that have stored metadata.
    """
    if not face_hashes:
        return {}
    conn = _get_conn()
    ph = ",".join("?" for _ in face_hashes)
    rows = conn.execute(
        f"SELECT face_hash, meta_json FROM face_meta WHERE face_hash IN ({ph})",
        face_hashes,
    ).fetchall()
    conn.close()
    return {h: json.loads(m) for h, m in rows}


def fuzzy_lookup_face(raw: dict,
                      tol_pos=FUZZY_TOL_POSITION,
                      tol_area=FUZZY_TOL_AREA,
                      tol_dim=FUZZY_TOL_DIM) -> tuple:
    """
    Fuzzy match: find a stored face whose geometry is within tolerance.

    Topology (surf_type, n_edges, n_verts) must match EXACTLY.
    Continuous values (centroid, area, dimensions) use absolute tolerance.

    Returns (face_hash, meta_dict) or (None, None) if no match.
    """
    conn = _get_conn()
    # First filter by exact topology (fast, uses index)
    candidates = conn.execute(
        """SELECT face_hash, meta_json, cx, cy, cz, area, dx, dy, dz
           FROM face_meta
           WHERE surf_type = ? AND n_edges = ? AND n_verts = ?
             AND cx BETWEEN ? AND ?
             AND cy BETWEEN ? AND ?
             AND cz BETWEEN ? AND ?""",
        (raw["surf_type"], raw["n_edges"], raw["n_verts"],
         raw["cx"] - tol_pos, raw["cx"] + tol_pos,
         raw["cy"] - tol_pos, raw["cy"] + tol_pos,
         raw["cz"] - tol_pos, raw["cz"] + tol_pos),
    ).fetchall()
    conn.close()

    best = None
    best_dist = float("inf")

    for fh, mj, cx, cy, cz, area, dx, dy, dz in candidates:
        # Check area tolerance
        if abs(area - raw["area"]) > tol_area:
            continue
        # Check dimension tolerance
        if (abs(dx - raw["dx"]) > tol_dim or
            abs(dy - raw["dy"]) > tol_dim or
            abs(dz - raw["dz"]) > tol_dim):
            continue

        # Compute distance (for picking the closest match if multiple)
        dist = math.sqrt(
            (cx - raw["cx"])**2 + (cy - raw["cy"])**2 + (cz - raw["cz"])**2
            + (area - raw["area"])**2
        )
        if dist < best_dist:
            best_dist = dist
            best = (fh, mj)

    if best:
        return best[0], json.loads(best[1])
    return None, None


def lookup_faces_batch(face_hashes: list[str],
                       face_raws: list[dict]) -> dict[str, dict]:
    """
    Batch lookup: try exact hash first, then fuzzy match for misses.
    Returns {hash: meta_dict} for all faces that found a match.
    """
    # Exact match first
    result = lookup_face_meta(face_hashes)

    # Fuzzy match for faces that didn't get an exact hit
    for i, (h, raw) in enumerate(zip(face_hashes, face_raws)):
        if h in result:
            continue
        if raw is None:
            continue
        fh, meta = fuzzy_lookup_face(raw)
        if meta:
            result[h] = meta

    return result


def delete_face_meta(face_hash: str):
    conn = _get_conn()
    conn.execute("DELETE FROM face_meta WHERE face_hash = ?", (face_hash,))
    conn.commit()
    conn.close()


def get_db_stats() -> dict:
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) FROM face_meta").fetchone()[0]
    conn.close()
    return {"total_faces": count, "db_path": DB_PATH}


# Initialize on import
init_db()
