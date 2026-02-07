# SCRIBE — Master System Prompt

> **One-shot specification for building a browser-based CAD markup tool.**  
> *"Like PDFs for CAD."*

---

## 🎯 MISSION

Build **SCRIBE** — a lightweight, browser-based STEP file viewer and annotation tool that enables engineers to visualize, tolerance, thread, color, and annotate 3D models with the ease of a PDF.

**The core insight**: STEP files are the universal interchange format of manufacturing. They cross every boundary — SolidWorks to Fusion, supplier to buyer, shop floor to QC. But they carry almost no semantic intent. SCRIBE changes that by embedding face-level metadata *directly into the STEP file itself*, creating a traveling document of engineering intent that survives CAD tool re-imports, re-exports, and format conversions.

A face is no longer just a face. It's a face with a tolerance of ±0.001", threaded 1/4-20 UNC, painted blue, with a note that says "datum A." And that meaning persists — in the file, through the database, across tools.

---

## 🏗️ ARCHITECTURE

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                            SCRIBE ARCHITECTURE                               │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   ┌──────────────┐      ┌──────────────────┐      ┌────────────────────────┐ │
│   │   Browser    │─────▶│    Flask API     │─────▶│  CadQuery / OCP (XDE)  │ │
│   │  (Three.js)  │◀─────│    (Python)      │◀─────│  STEP Read / Write /   │ │
│   │              │      │                  │      │  Tessellate / Color    │ │
│   └──────────────┘      └──────────────────┘      └────────────────────────┘ │
│         │                       │                                             │
│         │                       ▼                                             │
│         │                ┌──────────────┐                                     │
│         │                │   SQLite DB  │   Geometry-fingerprinted face       │
│         │                │  (face_db)   │   metadata with fuzzy matching      │
│         │                └──────────────┘                                     │
│         │                                                                     │
│         ▼                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────┐   │
│   │                       3D VIEWPORT (WebGL)                             │   │
│   │                                                                       │   │
│   │   • Orthographic camera       • Arcball rotation with damping         │   │
│   │   • Face picking (raycasting) • Multi-select (Shift/Ctrl+Click)      │   │
│   │   • Per-face color editing    • Tolerance heat map overlay           │   │
│   │   • Hole wizard grouping      • Quick view buttons (F/B/L/R/T/Bo)   │   │
│   │   • Edge rendering            • XYZ orientation gizmo               │   │
│   │   • Lighting presets           • Selection pulse animation           │   │
│   │                                                                       │   │
│   └───────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack
| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Flask 3.x + Gunicorn | REST API, file serving, model state management |
| **CAD Kernel** | CadQuery 2.6 + cadquery-ocp 7.8 | XDE document handling, STEP I/O, BRep tessellation, color injection |
| **Database** | SQLite3 via `face_db.py` | Geometry-fingerprinted face metadata with exact + fuzzy matching |
| **Frontend** | Three.js r160+ (ES modules) | WebGL rendering, BufferGeometry, raycasting |
| **UI** | Vanilla JS + CSS custom properties | Zero-dependency, sub-millisecond interactions |
| **Deployment** | Docker → GCP Cloud Run | Serverless, auto-scaling, persistent uploads |

### Design Principles
1. **CAD-First UX** — Orthographic views, arcball rotation, zoom-to-cursor — like SolidWorks, Fusion, NX
2. **Metadata Survives** — Annotations embed in the STEP file itself, not just as overlay; they survive CAD tool re-exports
3. **Zero-Dependency Frontend** — Vanilla JS/CSS only. No React, no Vue, no Tailwind, no build step
4. **Precision Aesthetic** — Clean, modern panels; monospace console; professional color palette
5. **Machinist Units** — Defaults to inches. Tolerance bands reflect real machining reality (0.0005" to 0.030")
6. **Instant Feedback** — Console logs every action. DB saves confirmed. Errors shown in red

---

## 📁 FILE STRUCTURE

```
scribe/
├── app.py                     # Flask routes — the single entry point
├── core/                      # Modular application logic
│   ├── __init__.py
│   ├── state.py               # ModelState singleton (XDE doc, face data, metadata)
│   ├── loader.py              # load_step_xcaf() — STEP reading + tessellation
│   ├── exporter.py            # export_step_xcaf() — STEP writing + color/metadata injection
│   ├── metadata.py            # 3-strategy metadata embed/extract engine
│   └── utils.py               # Color conversion helpers (hex ↔ RGB ↔ OCC)
├── face_db.py                 # SQLite face fingerprinting + exact/fuzzy matching
├── requirements.txt           # Python deps (cadquery-ocp, flask, gunicorn, numpy)
├── Dockerfile                 # GCP Cloud Run container (python:3.11-slim)
├── .dockerignore              # Excludes venv, __pycache__, .db, uploads, tests
├── static/
│   ├── css/
│   │   ├── style.css          # Core layout, CSS custom properties, dark toolbar, light panels
│   │   └── style_expansion.css # Right-panel expansion animations
│   └── js/
│       └── viewer.js          # Three.js viewer + ALL UI logic (~1600 lines)
├── templates/
│   └── index.html             # Single-page application (Jinja2)
├── tests/
│   ├── run_tests.py           # Test runner — executes all test files in subprocess isolation
│   ├── sample.step            # Default model auto-loaded on boot (machined part)
│   └── test_*.py              # 11 unit/integration tests
├── system_prompt.md           # This file — master specification
├── README.md                  # Technical overview for contributors
└── uploads/                   # User-uploaded STEP files (UUID-named, persisted)
```

---

## 📐 PAGE LAYOUT

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  TOOLBAR (36px, dark gradient)                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ SCRIBE  "like PDFs for CAD"  by Andrew McCalip │ ☀ Edge Fit │    UUID   │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────────────────┤
│ ┌──────────┐                                                ┌───┬───────────┐ │
│ │ LEFT     │                                                │ T │ RIGHT     │ │
│ │ SIDEBAR  │                                                │ A │ PANEL     │ │
│ │ 240px    │          ┌──────────────────────┐              │ B │           │ │
│ │          │          │                      │              │ S │ Props     │ │
│ │ [Import] │          │   3D VIEWPORT        │              │   │ - Face ID │ │
│ │ [Export] │          │   (Three.js WebGL)    │              │ 64│ - Type    │ │
│ │          │          │                      │              │ px│ - Color   │ │
│ │          │          │                      │              │   │ - Thread  │ │
│ │          │          │      [F][B][L][R]     │              │   │ - Tol     │ │
│ │          │          │      [T][Bo][Iso]     │              │   │ - Datum   │ │
│ │          │          └──────────────────────┘              │   │           │ │
│ │ ┌──────┐ │               [XYZ Gizmo]                      │   │           │ │
│ │ │CONSOL│ │                                                │   │           │ │
│ │ │  log │ │                                                │   │           │ │
│ │ │ DB|F │ │                                                │   │           │ │
│ │ └──────┘ │                                                │   │           │ │
│ └──────────┘                                                └───┴───────────┘ │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Panel Behavior
- **Left Sidebar (240px)**: Import drop zone, Export button, Console log pinned to bottom. Collapsible (36px icon-only). Admin cleanup buttons (DB/File/All) next to Console header.
- **Right Panel (350px)**: Context-sensitive. Three vertical tabs: **Props** | **Holes** | **Tols**. Tabs are always visible; panel slides out on first tab click.
- **Toolbar**: SCRIBE brand (clickable → home), subtitle, byline, center icon buttons (Light/Edge/Fit), UUID badge (right, selectable).

---

## 🖱️ INTERACTION CONTROLS

### Mouse Controls
| Action | Input |
|--------|-------|
| **Orbit** | Left-drag (arcball, 0.25 damping) |
| **Pan** | Right-drag |
| **Zoom** | Scroll wheel (zoom-to-cursor) |
| **Select Face** | Click |
| **Add to Selection** | Shift+Click or Ctrl+Click |
| **Deselect All** | Escape, or double-click background |

### Camera
- **Type**: Orthographic (CAD-standard, no perspective)
- **Default View**: Isometric from front-left-bottom `(-1, -1, 1)` with Z-up
- **View Buttons**: Floating bar at bottom-center — Front, Back, Left, Right, Top, Bottom, Iso
- **Rotation**: ArcballControls with damping (0.25) for fluid, weighted feel
- **Zoom**: Zoom-to-cursor algorithm preserves the point under the mouse

---

## 🔧 FEATURE SPECIFICATIONS

### 1. STEP File Import
```
POST /upload  →  multipart/form-data
  Accepts: .step, .stp
  Returns: { faces: [...], uuid: "...", filename: "..." }
  Redirects to: /view/{uuid}
```
- Drag-and-drop zone with upload icon + "or click to browse"
- Shows "Processing..." spinner during XDE read + tessellation
- Auto-loads `tests/sample.step` on first boot (no empty viewport)
- Each face is tessellated into indexed BufferGeometry (vertices, normals, indices)
- Face metadata recovered via: embedded STEP metadata → SQLite DB (exact hash → fuzzy match)

### 2. Face Selection & Properties Panel
- Click face → highlight with **pulsing pink glow** (`#ec4899`, sinusoidal emissive pulse)
- Multi-select with Shift/Ctrl+Click
- Right panel (Props tab) shows:
  - **Face ID**: First 8 chars of geometry hash
  - **Surface Type**: Plane, Cylinder, Cone, Sphere, BSpline, Other
  - **Area**: Calculated in in² from BRep
  - **Color Picker**: Sets the physical surface color (persists to DB + STEP export)
  - **Thread Dropdowns**: Type → Size cascading selection
  - **Tolerance Dropdowns**: Type → Value cascading selection
  - **Datum Input**: Free-text field (e.g., "A", "B|C")

### 3. Threading Metadata
```javascript
threadTypes: [
  "UNC (Unified National Coarse)",
  "UNF (Unified National Fine)",
  "M (ISO Metric)",
  "MF (ISO Metric Fine)",
  "Helicoil (UNC)",
  "Helicoil (UNF)",
  "Keensert (UNC)"
]
threadSizes: {
  "UNC": ["#2-56", "#4-40", "#6-32", "#8-32", "#10-24", "#10-32",
           "1/4-20", "5/16-18", "3/8-16", "7/16-14", "1/2-13"],
  "UNF": ["#4-48", "#6-40", "#8-36", "#10-32",
           "1/4-28", "5/16-24", "3/8-24", "1/2-20"],
  // Metric, Helicoil, Keensert sizes also available
}
threadClasses: ["1A/1B", "2A/2B", "3A/3B", "6g/6H (ISO)", "4g6g/4H5H (ISO)", "6e/6H (ISO)"]
```
- Thread metadata is applied per-face and persisted to DB + embedded in STEP export
- Face color can be set per thread group in the Hole Wizard

### 4. Tolerance Metadata
```javascript
toleranceTypes: [
  "None", "Linear +/-", "Limit",
  "H7 (Hole)", "H8 (Hole)", "g6 (Shaft)",
  "Flatness", "Parallelism", "Perpendicularity",
  "Position", "Concentricity", "Custom"
]

// Values are INCH-BASED machining tolerances (reflecting real shop floor reality)
toleranceValues: [
  "None",
  "+/- 0.0005", "+/- 0.001", "+/- 0.002", "+/- 0.003", "+/- 0.005",
  "+/- 0.010", "+/- 0.015", "+/- 0.020", "+/- 0.030",
  "+0.000/-0.001", "+0.001/-0.000", "+0.000/-0.005", "+0.005/-0.000",
  "0.001 TIR", "0.002 TIR", "0.005 TIR", "0.010 TIR"
]
```

### 5. Tolerance Heat Map Mode
- Activated via the **Tols** tab on the right panel
- Colors every face by its tolerance tightness:
  - **Tight** (≤ 0.005"): **Red** `#f44336` ← configurable via color picker
  - **Loose** (> 0.005"): **Gray** `#b0b0b0` ← configurable via color picker
  - **No Tolerance**: Ghosted / transparent
- **Checkboxes**: Filter by type (Linear ±, Limit, GD&T, Fits)
- **Tolerance Groups**: Expandable cards grouping faces by tolerance type
  - Each group has: eye icon (visibility toggle), color picker, face count badge, delete button
  - Click group header to expand/collapse face list
  - Click individual face to select it in the viewport
- Toggling heat map off restores all original face colors

### 6. Hole Wizard
- Activated via the **Holes** tab on the right panel
- Groups faces by **thread metadata** (user-defined, not just raw geometry)
  - Groups labeled like: "UNC 1/4-20", "M6x1 ISO Metric"
  - Each group has:
    - **Eye icon**: Toggle visibility (faces go transparent)
    - **Color picker**: Assign color to all faces in group
    - **Face count badge**: Pill showing number of faces
    - **Delete (×)**: Remove thread metadata from all faces in group
  - Click group header to expand face list
- **Cylindrical Faces Count**: Shows total unthreaded cylinders at bottom
- **"Holes by Diameter"**: Groups unthreaded cylindrical faces by measured diameter

### 7. Lighting System
- **Toolbar button** opens a floating modal over the viewport
- Modal contains:
  - **Preset selector**: Standard (3-Point), Flat (Even), Dramatic (High Contrast)
  - **Ambient Intensity**: Slider 0–2 (default 0.4)
  - **Key Light**: Slider 0–3 (default 1.0)
  - **Fill Light**: Slider 0–2 (default 0.5)
  - **Back Light**: Slider 0–2 (default 0.5)
- Modal has frosted glass aesthetic (`backdrop-filter: blur(10px)`, dark semi-transparent)
- Dismissed via × button; settings persist during session

### 8. Export
- Single **"Export"** button in the left sidebar
- Exports the model as a STEP file with:
  - **Face colors** embedded via XDE styled-items (CAD tools render them)
  - **Metadata** embedded via **three redundant strategies** for maximum survivability:
    1. `PROPERTY_DEFINITION` → `DESCRIPTIVE_REPRESENTATION_ITEM` entities (SolidWorks-compatible)
    2. `[SVFM:<base64>]` tag in the PRODUCT description field (universally preserved by all CAD tools)
    3. `/* __STEPVIEWER_META_START__ ... */` comment block (fast path for SCRIBE-to-SCRIBE)
- **Filename**: `{uuid}.step`
- Round-trip tested: Upload → Annotate → Export → Re-upload → All metadata recovered

### 9. Admin Cleanup Tools
- Located next to the Console header in the left sidebar (DB | File | All buttons)
- **Three scopes**:
  - **[DB]** (red): Delete face metadata from SQLite for this model's geometry hashes
  - **[File]** (amber): Strip all 3 embedded metadata strategies from the STEP file on disk
  - **[All]** (black): Global database wipe + file strip + in-memory clear
- **Critical behavior**: Always clears `model.face_meta = {}` regardless of scope, preventing stale metadata from re-injecting on the next export
- Before/after verification via `extract_meta_from_step()` with full server-side logging
- No page reload required — UI resets visually in-place

---

## 🧬 METADATA SYSTEM (Three-Strategy Engine)

The metadata system is the heart of SCRIBE. It solves a fundamental problem: **STEP files have no standard way to carry per-face semantic data.** SCRIBE injects metadata via three independent strategies, each targeting different survival characteristics:

### Strategy 1: DESCRIPTIVE_REPRESENTATION_ITEM (DRI)
```step
#100 = PROPERTY_DEFINITION('face_meta','',#101);
#101 = PROPERTY_DEFINITION_REPRESENTATION(#100,#102);
#102 = REPRESENTATION('',(#103),#104);
#103 = DESCRIPTIVE_REPRESENTATION_ITEM('SVFM','<base64-encoded JSON>');
```
- **Survives**: SolidWorks import/export, NX, CATIA
- **Mechanism**: Attaches a property to the PRODUCT_DEFINITION entity
- **Pros**: Standards-compliant ISO 10303-21, widely preserved
- **Cons**: Some tools strip orphaned property chains

### Strategy 2: PRODUCT Description Tag
```step
FILE_NAME('model.step [SVFM:eyJmYWNlX21ldGEi...]','2024-01-01',...);
```
- **Survives**: Nearly everything — FILE_NAME is universally preserved
- **Mechanism**: Base64-encoded JSON appended to the PRODUCT description field
- **Pros**: Maximum survivability, even through aggressive re-exporters
- **Cons**: Size-limited for very large metadata payloads

### Strategy 3: Comment Block (SCRIBE-to-SCRIBE)
```step
/* __STEPVIEWER_META_START__
eyJmYWNlX21ldGEiOiB7...}
__STEPVIEWER_META_END__ */
```
- **Survives**: SCRIBE re-imports only (most tools strip comments)
- **Mechanism**: Standard STEP comment block with sentinel markers
- **Pros**: Fastest to parse, unlimited size, human-readable location
- **Cons**: Fragile — any STEP re-export by another tool removes it

### Recovery Priority
When loading a STEP file, metadata is recovered in priority order:
1. **DRI entities** (Strategy 1) — checked first
2. **Description tag** (Strategy 2) — fallback
3. **Comment block** (Strategy 3) — last resort
4. **SQLite DB** — exact hash match, then fuzzy geometry match

---

## 💾 DATABASE SCHEMA

### `faces` Table (SQLite)
```sql
CREATE TABLE faces (
    id INTEGER PRIMARY KEY,
    face_hash TEXT UNIQUE NOT NULL,      -- 16-char hex geometry fingerprint
    meta TEXT DEFAULT '{}',              -- JSON blob: {color, thread, tolerance, datum, ...}

    -- Geometry fingerprint components (for fuzzy matching)
    surf_type TEXT,                       -- Plane, Cylinder, Cone, Sphere, BSpline, Other
    cx REAL, cy REAL, cz REAL,           -- Face centroid
    area REAL,                           -- Surface area
    dx REAL, dy REAL, dz REAL,           -- Bounding box dimensions
    n_edges INTEGER,                     -- Edge count
    n_verts INTEGER,                     -- Vertex count

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_faces_hash ON faces(face_hash);
```

### Face Fingerprinting Algorithm
The geometry fingerprint is a 16-character hex hash derived from:
1. **Surface type** (must match exactly)
2. **Centroid** (cx, cy, cz — rounded to 3 decimals)
3. **Area** (rounded to 3 decimals)
4. **Bounding box** (dx, dy, dz — rounded to 3 decimals)
5. **Topology** (n_edges, n_verts — must match exactly)

**Fuzzy matching** uses these tolerances when exact hash fails:
- Position: 10 microns (0.01mm)
- Area: 0.1 mm²
- Dimensions: 10 microns
- Topology: exact match required

---

## 🌐 API ENDPOINTS

| Method | Endpoint | Request | Response |
|--------|----------|---------|----------|
| `GET` | `/` | — | HTML (auto-loads `tests/sample.step`) |
| `GET` | `/view/{uuid}` | — | HTML (loads model by UUID) |
| `POST` | `/upload` | `multipart/form-data` (file) | `{ faces, uuid, filename }` |
| `GET` | `/model/{uuid}` | — | `{ faces }` |
| `POST` | `/set_color` | `{ face_id, color }` or `{ updates: [...] }` | `{ ok, db_updated_count }` |
| `POST` | `/set_thread` | `{ face_id, thread_type, thread_size, thread_class }` | `{ ok }` |
| `POST` | `/set_tolerance` | `{ updates: [{ face_id, tol_type, tol_value }] }` | `{ ok, updated }` |
| `GET` | `/thread_options` | — | `{ types, sizes, classes }` |
| `GET` | `/tolerance_options` | — | `{ types, values }` |
| `GET` | `/holes` | — | `{ holes: [{ diameter, count, face_ids }] }` |
| `POST` | `/export` | — | Binary `.step` file download |
| `GET` | `/db_stats` | — | `{ total_faces, faces_with_meta }` |
| `POST` | `/test_cube` | — | `{ faces }` (6-face test cube) |
| `GET` | `/test_sample` | — | `{ faces, filename }` |
| `POST` | `/api/admin/clear_metadata` | `{ scope: "db"|"file"|"all" }` | `{ ok, message, details }` |

---

## 🎨 VISUAL DESIGN SYSTEM

### Color Palette
```css
/* === Toolbar (Dark) === */
--bg-toolbar:     #2c2c2c;        /* Dark toolbar background */
--accent-blue:    #60a5fa;        /* Brand blue, active states */
--text-toolbar:   #94a3b8;        /* Muted toolbar text */

/* === Sidebar (Light) === */
--bg-sidebar:     #f4f5f7;        /* Light gray sidebar */
--bg-sidebar-alt: #eaecf0;        /* Hover/alternate rows */

/* === 3D Viewport === */
--face-default:   #90a4ae;        /* Neutral gray for uncolored faces */
--face-select:    #ec4899;        /* Pink selection glow */
--face-tight:     #f44336;        /* Red for tight tolerances */
--face-loose:     #b0b0b0;        /* Gray for loose tolerances */

/* === Right Panel (Light) === */
--accent:         #2563eb;        /* Primary blue (buttons, links) */
--accent-hover:   #1d4ed8;        /* Darker blue on hover */
--text:           #1e293b;        /* Dark text */
--text-dim:       #64748b;        /* Secondary/label text */
--border:         #d1d5db;        /* Panel borders */

/* === Console (Dark terminal) === */
--console-bg:     #1e1e2e;        /* Deep dark background */
--log-info:       #94a3b8;        /* Gray info lines */
--log-ok:         #4ade80;        /* Green success */
--log-warn:       #facc15;        /* Yellow warning */
--log-err:        #f87171;        /* Red error */
```

### Typography
```css
font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;

/* Brand: SCRIBE */
.scribe-brand { font-weight: 800; font-size: 1.25rem; color: #60a5fa; letter-spacing: -0.02em; }

/* Console */
font-family: 'Cascadia Code', 'Consolas', 'Monaco', monospace;
```

### Component Patterns
- **Thread/Tolerance Groups**: Light card (`#f1f5f9`), rounded, expandable header with eye/color/count/delete
- **Buttons (sidebar)**: Blue background, white text, subtle shadow, green for Export
- **Buttons (toolbar)**: Transparent, icon+label, hover → lighter background, active → blue icon
- **View Buttons**: Floating bar, 0.45 opacity → 0.95 on hover, minimal and unobtrusive
- **Modals**: Frosted glass (`backdrop-filter: blur(10px)`), dark semi-transparent
- **Inputs**: Light background, subtle border, focus → blue ring

---

## 🚀 DEPLOYMENT

### Dockerfile (GCP Cloud Run)
```dockerfile
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=8080
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
```

### Local Development
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py               # Starts on http://localhost:5555
```

### Key Dependencies
```
flask==3.1.2
werkzeug==3.1.5
gunicorn==20.1.0
cadquery==2.6.1
cadquery-ocp==7.8.1.1.post1
numpy==2.4.2
```

---

## 🧪 TESTING

### Test Suite (11 tests)
| Test | What It Verifies |
|------|-----------------|
| `test_boot.py` | Server starts, `/test_cube` returns 6 faces with correct geometry |
| `test_xde_pipeline.py` | Full XDE document round-trip: load → color → export → verify STYLED_ITEM |
| `test_geometry_db.py` | Face fingerprinting + SQLite persistence + fuzzy matching |
| `test_three_strategies.py` | All 3 metadata strategies inject/extract correctly |
| `test_thread.py` | Thread metadata set → persisted → recovered on reload |
| `test_step_entities.py` | STEP entity-level verification of injected metadata structures |
| `test_meta_roundtrip.py` | Full round-trip: color + thread + tolerance → export → re-upload → verify |
| `test_fuzzy_sw.py` | Fuzzy matching against SolidWorks re-exported STEP files |
| `test_db_restoration.py` | DB metadata restoration after model reload (pytest) |
| `test_hole_tolerance_suite.py` | Hole detection + tolerance assignment + heat map integration |
| `test_browser_flow.py` | Simulates full browser workflow: test_cube → set_color → export → re-upload |

### Running Tests
```bash
# Start the server first
python app.py

# Run the full suite (separate terminal)
python tests/run_tests.py

# Or use pytest for the pytest-based tests
python -m pytest tests/ -v
```

### Manual Verification Checklist
1. **Boot**: Visit `/` — sample model loads automatically, no empty viewport
2. **Face Selection**: Click face → pink glow pulse. Shift+Click → multi-select
3. **Color Persistence**: Set color → export → re-upload → color preserved
4. **Heat Map**: Enable Tols tab → faces colored by tolerance → disable → original colors restore
5. **Hole Wizard**: Enable Holes tab → thread groups rendered → color picker works → eye toggle works
6. **Export Round-Trip**: Annotate → Export → Re-upload → All metadata (color + thread + tolerance) recovered
7. **Admin Cleanup**: Click DB/File/All → metadata cleared → export produces clean STEP

---

## 🚫 EXCLUDED FEATURES

These were intentionally removed to keep the tool focused:

- ❌ Grid / axis display
- ❌ Perspective camera (orthographic only, like real CAD)
- ❌ Surface Finish section (roughness, finish process — not yet implemented)
- ❌ Material section (material, hardness — not yet implemented)
- ❌ Snap-to-grid
- ❌ Navigation help text overlay
- ❌ View Cube widget (replaced by floating view buttons)

---

## ⚡ CORE FUNCTIONS REFERENCE

### Backend (`core/`)

| Function | Module | Purpose |
|----------|--------|---------|
| `load_step_xcaf(path)` | `loader.py` | Read STEP via XDE, extract faces, tessellate, recover metadata |
| `export_step_xcaf()` | `exporter.py` | Write STEP with colors + metadata (3 strategies) |
| `inject_meta_into_step(path, meta)` | `metadata.py` | Post-write metadata injection into STEP file text |
| `extract_meta_from_step(path)` | `metadata.py` | Pre-read metadata extraction from STEP file text |
| `compute_face_hash(face)` | `face_db.py` | Generate 16-char hex geometry fingerprint |
| `upsert_face(hash, meta)` | `face_db.py` | Insert or update face metadata in SQLite |
| `fuzzy_match(fingerprint)` | `face_db.py` | Find closest matching face within tolerance bands |

### Frontend (`viewer.js`)

| Function | Purpose |
|----------|---------|
| `loadModel()` | Fetch face data from API, build BufferGeometry scene |
| `buildScene()` | Create Three.js meshes with per-face userData |
| `selectFace(mesh, additive)` | Highlight face, populate right panel |
| `applyHeatMap()` | Color faces by tolerance (tight=red, loose=gray) |
| `loadHoleManager()` | Render thread groups with eye/color/delete controls |
| `fitCameraToGroup()` | Auto-frame camera to fit model bounds (isometric default) |

---

> **Build this with the precision of a machinist and the elegance of a Swiss watch.** ⚙️
