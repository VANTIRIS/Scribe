"""
Flask app for loading STEP files with XDE (Extended Data Exchange).

Color metadata lives in XDE styled-items (native STEP).
Thread/tolerance metadata is embedded as **real STEP entities**:

  PROPERTY_DEFINITION → PROPERTY_DEFINITION_REPRESENTATION →
  REPRESENTATION → DESCRIPTIVE_REPRESENTATION_ITEM

This is the ISO 10303-214 standard mechanism for custom product properties.
The payload is base64-encoded JSON inside the DESCRIPTIVE_REPRESENTATION_ITEM
value string, which survives through CAD tools that preserve product properties.
A comment block is also written as a fast fallback for tool-to-tool round-trips.
"""

import base64
import io
import json
import logging
import os
import re
import uuid
import tempfile
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request, jsonify, send_file

# ── OCP (OpenCascade) imports ────────────────────────────────────────────────
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.XCAFApp import XCAFApp_Application
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import (
    XCAFDoc_DocumentTool,
    XCAFDoc_ColorSurf,
    XCAFDoc_ColorGen,
)
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool, BRep_Builder
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound
from OCP.gp import gp_Pnt
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

# ── Geometry fingerprinting + SQLite persistence ─────────────────────────────
from face_db import (
    face_fingerprint, face_fingerprint_raw, save_face_meta,
    lookup_faces_batch, get_db_stats,
)

# ── Flask setup ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ── Logging setup ────────────────────────────────────────────────────────────
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_logs.txt")
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# Also log werkzeug (Flask's HTTP server) to the same file
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addHandler(file_handler)
werkzeug_logger.setLevel(logging.INFO)

app.logger.info("Flask server starting up")

# ── Metadata markers ─────────────────────────────────────────────────────────
_SVFM_TAG       = "SVFM"                    # tag inside DESCRIPTIVE_REPRESENTATION_ITEM
_SVFM_PROP_NAME = "StepViewerFaceMetadata"  # PROPERTY_DEFINITION name
_SVFM_DESC_PFX  = "[SVFM:"                  # prefix in PRODUCT description
_SVFM_DESC_SFX  = "]"

# Comment fallback
_META_START = "/* __STEPVIEWER_META_START__ "
_META_END   = " __STEPVIEWER_META_END__ */"
_META_COMMENT_RE = re.compile(
    r"/\* __STEPVIEWER_META_START__ (.*?) __STEPVIEWER_META_END__ \*/",
    re.DOTALL,
)

# Entity extraction regex — matches either tag name (across line breaks)
_SVFM_ENTITY_RE = re.compile(
    r"DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'(?:" + _SVFM_TAG + r"|" + _SVFM_PROP_NAME + r")'\s*,\s*'([^']*)'\s*\)",
    re.DOTALL,
)

# PRODUCT description extraction regex
_SVFM_DESC_RE = re.compile(r"\[SVFM:([A-Za-z0-9+/=]+)\]")


# ── In-memory model state (single-user for simplicity) ──────────────────────
class ModelState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.doc = None
        self.xcaf_app = None
        self.shape_tool = None
        self.color_tool = None
        self.face_shapes = []
        self.face_labels = []
        self.face_hashes = []       # list[str] — geometry fingerprint per face
        self.face_raws = []         # list[dict] — raw fingerprint values per face
        self.face_meta = {}         # dict[int, dict] — per-face metadata
        self.original_filename = ""
        self.model_uuid = None      # unique identifier for current model


model = ModelState()


# ── Helpers ──────────────────────────────────────────────────────────────────

def hex_to_quantity(hex_color: str) -> Quantity_Color:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    return Quantity_Color(r, g, b, Quantity_TOC_RGB)


def quantity_to_hex(c: Quantity_Color) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(round(c.Red() * 255)),
        int(round(c.Green() * 255)),
        int(round(c.Blue() * 255)),
    )


def _get_face_color(color_tool, face_label, face_shape, parent_label):
    q = Quantity_Color()
    if face_label is not None and not face_label.IsNull():
        if color_tool.GetColor_s(face_label, XCAFDoc_ColorSurf, q):
            return quantity_to_hex(q)
        if color_tool.GetColor_s(face_label, XCAFDoc_ColorGen, q):
            return quantity_to_hex(q)
    if color_tool.GetColor(face_shape, XCAFDoc_ColorSurf, q):
        return quantity_to_hex(q)
    if color_tool.GetColor(face_shape, XCAFDoc_ColorGen, q):
        return quantity_to_hex(q)
    if parent_label is not None and not parent_label.IsNull():
        if color_tool.GetColor_s(parent_label, XCAFDoc_ColorSurf, q):
            return quantity_to_hex(q)
        if color_tool.GetColor_s(parent_label, XCAFDoc_ColorGen, q):
            return quantity_to_hex(q)
    return None


# ── Metadata embedding in STEP files ────────────────────────────────────────

def _decode_b64_meta(b64_str: str) -> dict:
    """Decode a base64 metadata payload, return {} on failure."""
    try:
        return json.loads(base64.b64decode(b64_str).decode("utf-8"))
    except Exception:
        return {}


def extract_meta_from_step(filepath: str) -> dict:
    """
    Extract embedded face metadata from a STEP file.

    Three strategies tried in priority order — the first one that yields
    data wins.  This gives us resilience across different CAD tools:

      1. DESCRIPTIVE_REPRESENTATION_ITEM('SVFM', '<b64>')
         Real STEP entity — survives tools that preserve product properties.

      2. PRODUCT description field  [SVFM:<b64>]
         The description is the most universally preserved text in STEP.
         SolidWorks maps it to "Description" custom property, Fusion 360
         keeps it as the component description.  Survives almost everything.

      3. Comment block  /* __STEPVIEWER_META_START__ ... */
         Fastest for our-tool-to-our-tool, but stripped by any re-export.
    """
    try:
        with open(filepath, "r", errors="replace") as f:
            text = f.read()

        # Strategy 1: STEP entity
        m = _SVFM_ENTITY_RE.search(text)
        if m:
            result = _decode_b64_meta(m.group(1))
            if result:
                return result

        # Strategy 2: PRODUCT description field
        m = _SVFM_DESC_RE.search(text)
        if m:
            result = _decode_b64_meta(m.group(1))
            if result:
                return result

        # Strategy 3: Comment block
        m = _META_COMMENT_RE.search(text)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

    except Exception:
        pass
    return {}


def inject_meta_into_step(step_bytes: bytes, meta: dict) -> bytes:
    """
    Inject face metadata into a STEP file using THREE strategies:

    1. PROPERTY_DEFINITION on PRODUCT_DEFINITION (not PRODUCT_DEFINITION_SHAPE!)
       This is how SolidWorks writes custom properties to STEP. When SW imports
       a file with PROPERTY_DEFINITION → PRODUCT_DEFINITION, it maps it to a
       custom property and re-exports it.  The entity chain:

         PROPERTY_DEFINITION('StepViewerFaceMetadata','',#PD)
         PROPERTY_DEFINITION_REPRESENTATION(→ REPRESENTATION)
         REPRESENTATION(→ DESCRIPTIVE_REPRESENTATION_ITEM)
         DESCRIPTIVE_REPRESENTATION_ITEM('SVFM','<base64>')

    2. PRODUCT description field — append [SVFM:<base64>] to the existing
       description.  This is the single most reliably preserved text field
       across ALL CAD tools (SolidWorks, Fusion 360, CATIA, NX, Creo).

    3. Comment block — fast fallback for our own tool.
    """
    if not meta:
        return step_bytes

    text = step_bytes.decode("utf-8", errors="replace")

    # Clean any existing meta (comment block, old description tag)
    text = _META_COMMENT_RE.sub("", text)

    # ── Encode payload ───────────────────────────────────────────────────
    payload_json = json.dumps(meta, separators=(",", ":"))
    payload_b64  = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")

    # ── Find STEP anchors ────────────────────────────────────────────────
    entity_ids = [int(x) for x in re.findall(r"#(\d+)\s*=", text)]
    max_id = max(entity_ids) if entity_ids else 0

    # PRODUCT_DEFINITION — the product-level entity that SolidWorks maps
    # to its internal product structure.  NOT PRODUCT_DEFINITION_SHAPE.
    # The regex uses \( to ensure we match exactly PRODUCT_DEFINITION and
    # not PRODUCT_DEFINITION_SHAPE or PRODUCT_DEFINITION_FORMATION.
    pd_match = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION\s*\(", text)

    # REPRESENTATION_CONTEXT
    ctx_match = re.search(
        r"#(\d+)\s*=\s*\(\s*GEOMETRIC_REPRESENTATION_CONTEXT", text
    )
    if not ctx_match:
        ctx_match = re.search(r"#(\d+)\s*=\s*REPRESENTATION_CONTEXT", text)

    # ── Strategy 1: PROPERTY_DEFINITION entities ─────────────────────────
    # Only use if payload is small enough effectively (prevent buffer overflow in readers)
    # 4KB limit is conservative safe zone for typical flex buffers (8KB-16KB)
    if len(payload_b64) < 4096:
        new_entities = ""
        if pd_match and ctx_match:
            pd_id  = pd_match.group(1)
            ctx_id = ctx_match.group(1)
            n = max_id + 1

            # Mirror the exact pattern SolidWorks uses for custom properties:
            new_entities = (
                f"#{n} = PROPERTY_DEFINITION('{_SVFM_PROP_NAME}','',#{pd_id});\n"
                f"#{n+1} = PROPERTY_DEFINITION_REPRESENTATION(#{n},#{n+2});\n"
                f"#{n+2} = REPRESENTATION('',(#{n+3}),#{ctx_id});\n"
                f"#{n+3} = DESCRIPTIVE_REPRESENTATION_ITEM('{_SVFM_PROP_NAME}',\n"
                f"  '{payload_b64}');\n"
            )

        # ── Strategy 2: Encode into PRODUCT description ──────────────────────
        # Also limit size here
        svfm_tag = f"{_SVFM_DESC_PFX}{payload_b64}{_SVFM_DESC_SFX}"

        # Remove any existing SVFM tag from product descriptions
        text = re.sub(r"\[SVFM:[A-Za-z0-9+/=]+\]", "", text)

        # Find PRODUCT entity — match the entity and its parameters
        product_re = re.compile(
            r"(#\d+\s*=\s*PRODUCT\s*\(\s*'[^']*'\s*,\s*')([^']*)('\s*,)",
            re.DOTALL,
        )
        m = product_re.search(text)
        if m:
            old_desc = m.group(2).strip()
            # Append our tag to existing description (preserve what's there)
            if old_desc:
                new_desc = f"{old_desc} {svfm_tag}"
            else:
                new_desc = svfm_tag
            text = text[:m.start(2)] + new_desc + text[m.end(2):]
    else:
        # Just clean up existing tags if we can't write new ones
        text = re.sub(r"\[SVFM:[A-Za-z0-9+/=]+\]", "", text)
        new_entities = ""

    # ── Strategy 3: Comment block ────────────────────────────────────────
    # Use indent=1 to break lines! This prevents "input buffer overflow" in flex scanners.
    # The regex in extract_meta matches DOTALL, so multiline JSON is fine.
    payload_multiline = json.dumps(meta, indent=1)
    comment = f"{_META_START}\n{payload_multiline}\n{_META_END}\n"

    # ── Inject entities + comment before ENDSEC; ─────────────────────────
    endsec_idx = text.rfind("ENDSEC;")
    if endsec_idx >= 0:
        text = text[:endsec_idx] + new_entities + comment + text[endsec_idx:]
    else:
        text += new_entities + comment

    return text.encode("utf-8")


# ── STEP loading with XDE ────────────────────────────────────────────────────

def load_step_xcaf(filepath: str, linear_deflection=0.1, angular_deflection=0.5):
    """
    Read a STEP file into an XDE document, tessellate every face, and return
    per-face mesh data together with any existing colour/thread metadata.
    """
    # ── Extract embedded metadata BEFORE OCC reads the file ──────────────
    embedded_meta = extract_meta_from_step(filepath)
    embedded_face_meta = embedded_meta.get("face_meta", {})

    # Create XDE application + document
    xcaf_app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    xcaf_app.InitDocument(doc)

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetLayerMode(True)

    status = reader.ReadFile(filepath)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Failed to read STEP file (status {status})")

    if not reader.Transfer(doc):
        raise RuntimeError("Failed to transfer STEP data to XDE document")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(labels)
    if labels.Size() == 0:
        raise RuntimeError("No shapes found in STEP file")

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    shape_labels = []
    for i in range(1, labels.Size() + 1):
        lbl = labels.Value(i)
        shape_labels.append(lbl)
        builder.Add(compound, shape_tool.GetShape_s(lbl))

    mesh = BRepMesh_IncrementalMesh(compound, linear_deflection, False, angular_deflection, True)
    mesh.Perform()

    face_shapes = []
    face_labels = []
    face_parent_labels = []

    for parent_label in shape_labels:
        parent_shape = shape_tool.GetShape_s(parent_label)
        explorer = TopExp_Explorer(parent_shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            face_shapes.append(face)
            face_label = shape_tool.AddSubShape(parent_label, face)
            face_labels.append(face_label if (face_label and not face_label.IsNull()) else None)
            face_parent_labels.append(parent_label)
            explorer.Next()

    # ── Compute geometry fingerprints for every face ────────────────────
    face_hashes = []
    face_raws   = []
    for face in face_shapes:
        try:
            raw = face_fingerprint_raw(face)
            h   = face_fingerprint(face)
        except Exception:
            raw = None
            h   = "unknown"
        face_hashes.append(h)
        face_raws.append(raw)

    # ── Restore metadata: embedded STEP > SQLite DB (exact+fuzzy) > empty
    
    # 1. Embedded Metadata (Index-based - Legacy/Fragile)
    face_meta_by_idx = {int(k): v for k, v in embedded_face_meta.items()}
    if embedded_face_meta:
        print(f"[META] Restored {len(embedded_face_meta)} faces from embedded index-based metadata")

    # 2. Embedded Metadata (Hash-based - Robust)
    embedded_hash_meta = embedded_meta.get("face_meta_by_hash", {})
    if embedded_hash_meta:
        restored_count = 0
        for idx, h in enumerate(face_hashes):
            if h in embedded_hash_meta:
                # Hash match from the file itself takes precedence over index
                # (unless index match exists? No, hash is safer if indices shifted)
                face_meta_by_idx[idx] = embedded_hash_meta[h]
                restored_count += 1
        print(f"[META] Restored {restored_count} faces from embedded hash-based metadata")

    # For any face WITHOUT embedded metadata, try SQLite lookup
    # (exact hash first, then fuzzy tolerance match)
    db_results = lookup_faces_batch(face_hashes, face_raws)
    print(f"[META] DB lookup: {len(db_results)} matches found for {len(face_hashes)} faces")
    db_restored = 0
    for idx, h in enumerate(face_hashes):
        # DB lookup takes precedence over embedded metadata (local overrides file)
        if h in db_results:
            # If we already have embedded meta, we could merge, but DB is strictly newer/user-defined
            # in this workflow. So we overwrite.
            face_meta_by_idx[idx] = db_results[h]
            db_restored += 1
            # print(f"[META] Face #{idx} restored from DB (hash={h[:8]}...): {db_results[h]}")
    if db_restored:
        print(f"[META] Total {db_restored} faces restored from SQLite DB")

    # ── Store state ──────────────────────────────────────────────────────
    model.doc = doc
    model.xcaf_app = xcaf_app
    model.shape_tool = shape_tool
    model.color_tool = color_tool
    model.face_shapes = face_shapes
    model.face_labels = face_labels
    model.face_hashes = face_hashes
    model.face_raws   = face_raws
    model.face_meta   = face_meta_by_idx

    # ── Tessellate + build response ──────────────────────────────────────
    faces_data = []
    db_restored = 0

    for idx, (face, face_label, parent_label) in enumerate(
        zip(face_shapes, face_labels, face_parent_labels)
    ):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue

        trsf = loc.Transformation()

        vertices = []
        for i in range(1, tri.NbNodes() + 1):
            node = tri.Node(i)
            pt = gp_Pnt(node.X(), node.Y(), node.Z())
            pt.Transform(trsf)
            vertices.extend([pt.X(), pt.Y(), pt.Z()])

        normals = []
        if tri.HasNormals():
            for i in range(1, tri.NbNodes() + 1):
                n = tri.Normal(i)
                normals.extend([n.X(), n.Y(), n.Z()])

        indices = []
        for i in range(1, tri.NbTriangles() + 1):
            t = tri.Triangle(i)
            n1, n2, n3 = t.Get()
            indices.extend([n1 - 1, n2 - 1, n3 - 1])

        hex_color = _get_face_color(color_tool, face_label, face, parent_label)
        meta = model.face_meta.get(idx, {})
        
        # Prefer DB-restored color over STEP file XDE color
        final_color = meta.get("color") or hex_color
        
        if idx not in {int(k) for k in embedded_face_meta} and meta:
            db_restored += 1

        faces_data.append({
            "id": idx,
            "vertices": vertices,
            "normals": normals,
            "indices": indices,
            "color": final_color,
            "thread": meta.get("thread"),
            "tolerance": meta.get("tolerance"),
            "face_hash": face_hashes[idx] if idx < len(face_hashes) else None,
        })

    return faces_data


# ── Routes ───────────────────────────────────────────────────────────────────


FIRST_BOOT = True

@app.route("/")
def index():
    global FIRST_BOOT
    do_test = FIRST_BOOT
    FIRST_BOOT = False
    return render_template("index.html", boot_test=do_test)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No selected file"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".step", ".stp"):
        return jsonify({"error": "Only .step / .stp files are supported"}), 400

    save_name = f"{uuid.uuid4().hex}.step"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], save_name)
    f.save(save_path)
    model.original_filename = os.path.splitext(f.filename)[0]
    
    # Store UUID based on filename
    model.model_uuid = os.path.splitext(save_name)[0]

    try:
        faces = load_step_xcaf(save_path)
    except Exception as e:
        app.logger.error(f"Upload failed: {e}", exc_info=True)
        model.reset()
        if os.path.exists(save_path): os.remove(save_path)
        return jsonify({"error": str(e)}), 500

    # Don't delete file - keep for persistence
    return jsonify({"faces": faces, "uuid": model.model_uuid})

@app.route("/<uuid_str>")
def view_model(uuid_str):
    """Serve the viewer for a specific model UUID."""
    return render_template("index.html", boot_test=False)

@app.route("/api/model/<uuid_str>")
def get_model(uuid_str):
    """Retrieve face data for a persisted model."""
    path = os.path.join(app.config["UPLOAD_FOLDER"], f"{uuid_str}.step")
    if not os.path.exists(path):
        return jsonify({"error": "Model not found"}), 404
        
    try:
        # Load the specific file into the global model object (single user limitation accepted)
        model.reset()
        model.model_uuid = uuid_str
        faces = load_step_xcaf(path)
        return jsonify({"faces": faces, "uuid": uuid_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/set_color", methods=["POST"])
def set_color():
    if model.doc is None:
        return jsonify({"error": "No model loaded"}), 400

    data = request.get_json()
    updates = data.get("updates")
    
    # Backward compatibility for single update
    if updates is None:
        updates = [{"face_id": data.get("face_id"), "color": data.get("color")}]

    db_updated_count = 0
    
    for item in updates:
        face_id = item.get("face_id")
        hex_color = item.get("color")

        if face_id is None or hex_color is None: continue
        if face_id < 0 or face_id >= len(model.face_shapes): continue

        try:
            q_color = hex_to_quantity(hex_color)
            face_label = model.face_labels[face_id]
            face_shape = model.face_shapes[face_id]
            if face_label is not None and not face_label.IsNull():
                model.color_tool.SetColor(face_label, q_color, XCAFDoc_ColorSurf)
            else:
                model.color_tool.SetColor(face_shape, q_color, XCAFDoc_ColorSurf)

            # ── Persist to Metadata & DB ────────────────────────────────────
            model.face_meta.setdefault(face_id, {})["color"] = hex_color
            
            if face_id < len(model.face_hashes):
                fh = model.face_hashes[face_id]
                raw = model.face_raws[face_id] if face_id < len(model.face_raws) else None
                if fh and fh != "unknown":
                    meta = model.face_meta.get(face_id, {})
                    if meta:
                        save_face_meta(fh, meta, raw=raw)
                        db_updated_count += 1

        except Exception as e:
            print(f"Error setting color for face {face_id}: {e}")
            continue

    return jsonify({"ok": True, "db_updated_count": db_updated_count})




@app.route("/export", methods=["GET"])
def export_step():
    """Re-export STEP with colours (XDE) + metadata (comment block)."""
    if model.doc is None:
        return jsonify({"error": "No model loaded"}), 400

    export_path = os.path.join(
        app.config["UPLOAD_FOLDER"], f"{uuid.uuid4().hex}_export.step"
    )

    try:
        writer = STEPCAFControl_Writer()
        writer.SetColorMode(True)
        writer.SetNameMode(True)
        writer.SetLayerMode(True)

        if not writer.Transfer(model.doc, STEPControl_AsIs):
            raise RuntimeError("Writer transfer failed")

        status = writer.Write(export_path)
        if status != IFSelect_RetDone:
            raise RuntimeError(f"Write failed (status {status})")

        with open(export_path, "rb") as ef:
            file_bytes = ef.read()

        # ── Inject metadata into the STEP file ──────────────────────────
        # Only include faces that have metadata
        if model.face_meta:
            # Legacy index-based metadata (for backward compat)
            meta_payload = {"face_meta": {str(k): v for k, v in model.face_meta.items()}}
            
            # Robust hash-based metadata (resilient to face reordering)
            # Map face_id -> face_hash -> metadata
            meta_by_hash = {}
            for face_id, meta in model.face_meta.items():
                if face_id < len(model.face_hashes):
                    fh = model.face_hashes[face_id]
                    if fh and fh != "unknown":
                        meta_by_hash[fh] = meta
            
            if meta_by_hash:
                meta_payload["face_meta_by_hash"] = meta_by_hash

            file_bytes = inject_meta_into_step(file_bytes, meta_payload)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(export_path):
            os.remove(export_path)

    download_name = f"{model.original_filename}_colored.step"
    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/octet-stream",
    )


@app.route("/set_thread", methods=["POST"])
def set_thread():
    """Store thread metadata for a face (batch support)."""
    if model.doc is None:
        return jsonify({"error": "No model loaded"}), 400

    data = request.get_json()
    updates = data.get("updates")
    
    if updates is None:
        updates = [{"face_id": data.get("face_id"), "thread": data.get("thread")}]

    db_updated_count = 0

    for item in updates:
        face_id = item.get("face_id")
        thread = item.get("thread")

        if face_id is None: continue
        if face_id < 0 or face_id >= len(model.face_shapes): continue

        if thread:
            model.face_meta.setdefault(face_id, {})["thread"] = {
                "type":  thread.get("type", ""),
                "size":  thread.get("size", ""),
                "pitch": thread.get("pitch", ""),
                "class": thread.get("class", ""),
            }
        else:
            if face_id in model.face_meta:
                model.face_meta[face_id].pop("thread", None)
                if not model.face_meta[face_id]:
                    del model.face_meta[face_id]

        # ── Persist to SQLite by geometry hash
        if face_id < len(model.face_hashes):
            fh = model.face_hashes[face_id]
            raw = model.face_raws[face_id] if face_id < len(model.face_raws) else None
            if fh and fh != "unknown":
                meta = model.face_meta.get(face_id, {})
                if meta:
                    save_face_meta(fh, meta, raw=raw)
                    db_updated_count += 1
                    # print(f"[DB] Updated Face #{face_id} thread metadata")

    return jsonify({"ok": True, "db_updated_count": db_updated_count})


@app.route("/thread_options", methods=["GET"])
def thread_options():
    """Return the standard option lists for thread dropdowns."""
    return jsonify({
        "types": [
            "None",
            "UNC (Unified Coarse)",
            "UNF (Unified Fine)",
            "M (ISO Metric)",
            "MF (ISO Metric Fine)",
            "STI (Helicoil Insert)",
            "Keensert",
            "UNEF (Unified Extra Fine)",
            "BSW (British Whitworth)",
            "BSF (British Fine)",
            "NPT (National Pipe Taper)",
            "NPTF (Dryseal Pipe)",
            "BSPT (British Pipe Taper)",
            "BSPP (British Pipe Parallel)",
            "Tr (Trapezoidal)",
            "ACME",
            "Buttress",
            "Custom",
        ],
        "sizes": {
            "M (ISO Metric)": [
                "M1", "M1.2", "M1.4", "M1.6", "M2", "M2.5", "M3", "M4", "M5",
                "M6", "M8", "M10", "M12", "M14", "M16", "M18", "M20", "M22",
                "M24", "M27", "M30", "M33", "M36", "M39", "M42", "M48", "M56", "M64",
            ],
            "MF (ISO Metric Fine)": [
                "M8x1", "M10x1", "M10x1.25", "M12x1.25", "M12x1.5",
                "M14x1.5", "M16x1.5", "M18x1.5", "M20x1.5", "M20x2",
                "M22x1.5", "M24x2", "M27x2", "M30x2", "M33x2", "M36x3",
            ],
            "UNC (Unified Coarse)": [
                "#0-80", "#1-64", "#2-56", "#3-48", "#4-40", "#5-40",
                "#6-32", "#8-32", "#10-24", "#12-24",
                "1/4-20", "5/16-18", "3/8-16", "7/16-14", "1/2-13",
                "9/16-12", "5/8-11", "3/4-10", "7/8-9", "1-8",
                "1-1/8-7", "1-1/4-7", "1-3/8-6", "1-1/2-6",
                "1-3/4-5", "2-4.5",
            ],
            "UNF (Unified Fine)": [
                "#0-80", "#1-72", "#2-64", "#3-56", "#4-48", "#5-44",
                "#6-40", "#8-36", "#10-32", "#12-28",
                "1/4-28", "5/16-24", "3/8-24", "7/16-20", "1/2-20",
                "9/16-18", "5/8-18", "3/4-16", "7/8-14", "1-12",
                "1-1/8-12", "1-1/4-12", "1-1/2-12",
            ],
            "UNEF (Unified Extra Fine)": [
                "1/4-32", "5/16-32", "3/8-32", "7/16-28", "1/2-28",
                "9/16-24", "5/8-24", "3/4-20", "7/8-20", "1-20",
            ],
            "STI (Helicoil Insert)": [
                "#2-56", "#4-40", "#6-32", "#8-32", "#10-24", "#10-32",
                "1/4-20", "1/4-28", "5/16-18", "5/16-24",
                "3/8-16", "3/8-24", "7/16-14", "7/16-20",
                "1/2-13", "1/2-20", "5/8-11", "5/8-18",
                "3/4-10", "3/4-16", "M3x0.5", "M4x0.7", "M5x0.8",
                "M6x1", "M8x1.25", "M10x1.5", "M12x1.75",
            ],
            "Keensert": [
                "#4-40", "#6-32", "#8-32", "#10-24", "#10-32",
                "1/4-20", "1/4-28", "5/16-18", "3/8-16", "7/16-14",
                "1/2-13", "1/2-20", "5/8-11", "3/4-10",
                "M3x0.5", "M4x0.7", "M5x0.8", "M6x1",
                "M8x1.25", "M10x1.5", "M12x1.75", "M16x2",
            ],
            "NPT (National Pipe Taper)": [
                '1/16-27', '1/8-27', '1/4-18', '3/8-18', '1/2-14',
                '3/4-14', '1-11.5', '1-1/4-11.5', '1-1/2-11.5', '2-11.5',
            ],
            "BSPP (British Pipe Parallel)": [
                'G1/8', 'G1/4', 'G3/8', 'G1/2', 'G3/4', 'G1', 'G1-1/4', 'G1-1/2', 'G2',
            ],
        },
        "pitches": {
            "M (ISO Metric)": [
                "0.25", "0.3", "0.35", "0.4", "0.45", "0.5", "0.6", "0.7",
                "0.75", "0.8", "1.0", "1.25", "1.5", "1.75", "2.0", "2.5",
                "3.0", "3.5", "4.0", "4.5", "5.0", "5.5", "6.0",
            ],
            "MF (ISO Metric Fine)": [
                "0.2", "0.25", "0.35", "0.5", "0.75", "1.0", "1.25", "1.5", "2.0", "3.0",
            ],
            "UNC (Unified Coarse)": [
                "80 TPI", "72 TPI", "64 TPI", "56 TPI", "48 TPI", "44 TPI",
                "40 TPI", "32 TPI", "24 TPI", "20 TPI", "18 TPI", "16 TPI",
                "14 TPI", "13 TPI", "12 TPI", "11 TPI", "10 TPI", "9 TPI",
                "8 TPI", "7 TPI", "6 TPI", "5 TPI", "4.5 TPI", "4 TPI",
            ],
            "UNF (Unified Fine)": [
                "80 TPI", "72 TPI", "64 TPI", "56 TPI", "48 TPI", "44 TPI",
                "40 TPI", "36 TPI", "32 TPI", "28 TPI", "24 TPI", "20 TPI",
                "18 TPI", "16 TPI", "14 TPI", "12 TPI",
            ],
            "NPT (National Pipe Taper)": [
                "27 TPI", "18 TPI", "14 TPI", "11.5 TPI", "8 TPI",
            ],
        },
        "classes": [
            "None",
            "1A / 1B (Loose)",
            "2A / 2B (Standard)",
            "3A / 3B (Tight)",
            "4g6g / 6H (ISO Loose)",
            "6g / 6H (ISO Medium)",
            "4h6h / 5H (ISO Close)",
            "6e / 6H (ISO Sliding)",
            "Interference",
            "Custom",
        ],
    })


@app.route("/get_holes", methods=["GET"])
def get_holes():
    """Analyze model and return grouped holes (cylindrical faces)."""
    if model.doc is None: return jsonify({"error": "No model loaded"}), 400
    
    holes = []
    # Simple hole detection: find all faces that are cylindrical
    # Refinement: check if internal (concave)? XDE doesn't give this easily without topology analysis.
    # For now, we list all cylindrical surfaces.
    
    # helper to check if cylinder
    def get_cylinder_info(face_shape):
        surf = BRepAdaptor_Surface(face_shape, True) # True = restriction to face
        if surf.GetType() == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            r = cyl.Radius()
            return {"type": "cylinder", "diameter": round(r * 2, 4)}
        return None

    grouped = {} # diameter -> list of face_ids

    for i, shape in enumerate(model.face_shapes):
        info = get_cylinder_info(shape)
        if info:
            d = info["diameter"]
            grouped.setdefault(d, []).append(i)

    # Format for frontend: list of groups
    # [{diameter: 10.0, ids: [1, 2, 3], count: 3}, ...]
    result = []
    for d, ids in grouped.items():
        result.append({"diameter": d, "ids": ids, "count": len(ids)})
    
    # Sort by diameter
    result.sort(key=lambda x: x["diameter"])
    
    return jsonify({"holes": result})

@app.route("/set_tolerance", methods=["POST"])
def set_tolerance():
    """Store tolerance metadata for a face (batch support)."""
    if model.doc is None: return jsonify({"error": "No model loaded"}), 400

    data = request.get_json()
    updates = data.get("updates")
    
    if updates is None:
        updates = [{"face_id": data.get("face_id"), "tolerance": data.get("tolerance")}]

    db_updated_count = 0

    for item in updates:
        face_id = item.get("face_id")
        tol = item.get("tolerance")

        if face_id is None: continue
        if face_id < 0 or face_id >= len(model.face_shapes): continue

        if tol:
            model.face_meta.setdefault(face_id, {})["tolerance"] = {
                "type": tol.get("type", ""),
                "value": tol.get("value", ""),
                "datum": tol.get("datum", ""),
            }
        else:
            if face_id in model.face_meta:
                model.face_meta[face_id].pop("tolerance", None)
                if not model.face_meta[face_id]: del model.face_meta[face_id]

        # Persist to SQLite
        if face_id < len(model.face_hashes):
            fh = model.face_hashes[face_id]
            if fh and fh != "unknown":
                meta = model.face_meta.get(face_id, {})
                if meta:
                    save_face_meta(fh, meta, raw=model.face_raws[face_id] if face_id < len(model.face_raws) else None)
                    db_updated_count += 1

    return jsonify({"ok": True, "db_updated_count": db_updated_count})

@app.route("/tolerance_options", methods=["GET"])
def tolerance_options():
    """Return standard tolerance options."""
    return jsonify({
        "types": [
            "None", "Linear +/-", "Limit", "Geometric (GD&T)", 
            "Position", "Flatness", "Parallelism", "Perpendicularity", 
            "Concentricity", "H7 (Hole)", "H8 (Hole)", "H9 (Hole)", 
            "g6 (Shaft)", "f7 (Shaft)", "h6 (Shaft)", "h7 (Shaft)", 
            "Custom"
        ],
        "values": [
            "None", 
            "+/- 0.0005", "+/- 0.001", "+/- 0.002", "+/- 0.003", "+/- 0.005",
            "+/- 0.010", "+/- 0.015", "+/- 0.020", "+/- 0.030",
            "+0.000/-0.001", "+0.001/-0.000", "+0.000/-0.005", "+0.005/-0.000",
            "0.001 TIR", "0.002 TIR", "0.005 TIR", "0.010 TIR"
        ]
    })

@app.route("/db_stats", methods=["GET"])
def db_stats():
    """Return geometry DB statistics."""
    return jsonify(get_db_stats())


@app.route("/test_cube", methods=["POST"])
def test_cube():
    try:
        import cadquery as cq
        tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
        tmp_path = tmp.name
        tmp.close()
        box = cq.Workplane("XY").box(20, 20, 20)
        cq.exporters.export(box, tmp_path)
        model.original_filename = "test_cube"
        faces = load_step_xcaf(tmp_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
    return jsonify({"faces": faces})


@app.route("/mockups")
def mockups():
    """Serve the feature mockups page."""
    return render_template("mockups.html")

@app.route('/test_sample', methods=['GET'])
def test_sample():
    """Loads tests/sample.STEP directly."""
    sample_path = os.path.join(app.root_path, 'tests', 'sample.STEP')
    if not os.path.exists(sample_path):
        return jsonify({"error": "Sample file not found"}), 404
        
    try:
        model.original_filename = "sample"
        faces = load_step_xcaf(sample_path)
        return jsonify({"faces": faces, "filename": "sample.STEP"})
    except Exception as e:
        print(f"Sample load error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5555)
