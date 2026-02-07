"""Compare OCC vs SolidWorks fingerprints after fixing the hash algorithm."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from face_db import face_fingerprint

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.XCAFApp import XCAFApp_Application
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS

def load_faces(filepath):
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.InitDocument(doc)
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True); reader.SetNameMode(True)
    assert reader.ReadFile(filepath) == IFSelect_RetDone
    reader.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = TDF_LabelSequence()
    st.GetFreeShapes(labels)
    faces = []
    for i in range(1, labels.Size() + 1):
        shape = st.GetShape_s(labels.Value(i))
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            faces.append(TopoDS.Face_s(exp.Current()))
            exp.Next()
    return faces

import cadquery as cq, tempfile
tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False); tmp.close()
cq.Workplane("XY").box(20,20,20).val().exportStep(tmp.name)

occ_faces = load_faces(tmp.name)
sw_faces  = load_faces(r"c:\repo_cad\cube export 4.STEP")
os.remove(tmp.name)

occ_hashes = {face_fingerprint(f) for f in occ_faces}
sw_hashes  = {face_fingerprint(f) for f in sw_faces}

print("OCC face hashes:")
for i, f in enumerate(occ_faces):
    print(f"  Face {i}: {face_fingerprint(f)}")

print("\nSW face hashes:")
for i, f in enumerate(sw_faces):
    print(f"  Face {i}: {face_fingerprint(f)}")

common = occ_hashes & sw_hashes
only_occ = occ_hashes - sw_hashes
only_sw  = sw_hashes - occ_hashes

print(f"\nMatching hashes: {len(common)}/{len(occ_hashes)}")
print(f"Only in OCC: {len(only_occ)}")
print(f"Only in SW:  {len(only_sw)}")

if common == occ_hashes == sw_hashes:
    print("\nPERFECT MATCH - all face fingerprints are identical!")
else:
    print("\nMISMATCH - some faces don't match")
    if only_occ: print(f"  OCC-only: {only_occ}")
    if only_sw:  print(f"  SW-only:  {only_sw}")
