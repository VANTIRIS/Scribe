
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool

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


# Global model instance
model = ModelState()
