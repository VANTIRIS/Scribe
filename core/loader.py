
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.XCAFApp import XCAFApp_Application
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import (
    XCAFDoc_DocumentTool,
    XCAFDoc_ColorSurf,
    XCAFDoc_ColorGen,
)
from OCP.TDF import TDF_LabelSequence
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.BRep import BRep_Tool, BRep_Builder
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Pnt

from face_db import (
    face_fingerprint, face_fingerprint_raw, save_face_meta,
    lookup_faces_batch
)
from core.state import model
from core.utils import _get_face_color
from core.metadata import extract_meta_from_step


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
