# SCRIBE — Master System Prompt

> **One-shot specification for building a browser-based CAD markup tool.**
> "Like PDFs for CAD"

---

## 🎯 MISSION

Build **SCRIBE**, a lightweight, browser-based STEP file viewer and annotation tool that enables engineers to visualize, tolerance, and annotate 3D models with the ease a PDF. It creates a "digital twin" that preserves metadata _inside_ the STEP file itself, surviving CAD tool re-exports.

---

## 🏗️ ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SCRIBE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐     ┌──────────────┐     ┌─────────────────────────────┐ │
│   │   Browser   │────▶│  Flask API   │────▶│   CadQuery / OCP (XDE)      │ │
│   │  (Three.js) │◀────│  (Python)    │◀────│   STEP Read/Write/Tessellate│ │
│   └─────────────┘     └──────────────┘     └─────────────────────────────┘ │
│         │                    │                                              │
│         │                    ▼                                              │
│         │             ┌──────────────┐                                      │
│         │             │   SQLite DB  │                                      │
│         │             │  (face_db)   │                                      │
│         │             └──────────────┘                                      │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     3D VIEWPORT (WebGL)                             │   │
│   │  • Orthographic camera • Arcball rotation • View cube              │   │
│   │  • Face picking • Multi-select • Color editing • Heat map          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stack
| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Flask 3.x + Gunicorn | REST API, file handling |
| **CAD Engine** | CadQuery 2.6 + cadquery-ocp | XDE document handling, STEP I/O, tessellation |
| **Database** | SQLite3 | Geometry-fingerprinted face metadata |
| **Frontend** | Three.js (ES modules) | WebGL rendering, interaction |
| **UI** | Vanilla JS + CSS | Zero-dependency, performant |
| **Deployment** | Docker → GCP Cloud Run | Scalable, serverless |

---

## 📁 FILE STRUCTURE

```
scribe/
├── app.py                  # Flask routes + STEP processing (XDE)
├── face_db.py              # SQLite face fingerprinting & metadata
├── requirements.txt        # Python dependencies (cadquery-ocp, flask, gunicorn)
├── Dockerfile              # GCP deployment container
├── .dockerignore           # Exclude venv, dev files
├── static/
│   ├── css/
│   │   ├── style.css               # Core dark theme
│   │   └── style_expansion.css     # Panel expansion styles
│   └── js/
│       └── viewer.js               # Three.js viewer + all UI logic
├── templates/
│   └── index.html          # Single-page application
├── tests/
│   └── sample.STEP         # Default model loaded on boot
└── uploads/                # User-uploaded files (temp)
```

---

## 🎨 VISUAL DESIGN SYSTEM

### Color Palette (Dark Theme)
```css
/* Background Layers */
--bg-base:      #0f0f0f;       /* Deepest background */
--bg-panel:     #111827;       /* Panel backgrounds */
--bg-elevated:  #1f2937;       /* Cards, modals, sections */
--bg-hover:     #374151;       /* Hover states */

/* Accent Colors */
--accent-blue:  #60a5fa;       /* Primary brand, links, active states */
--accent-glow:  rgba(96, 165, 250, 0.3);  /* Subtle glow effects */

/* Text Hierarchy */
--text-primary:   #e5e7eb;     /* Main content */
--text-secondary: #9ca3af;     /* Labels, hints */
--text-muted:     rgba(255, 255, 255, 0.5);  /* Subtle text */

/* Semantic Colors */
--color-tight:  #ef4444;       /* Tight tolerances (red) */
--color-loose:  #94a3b8;       /* Loose tolerances (gray) */
--color-select: #ec4899;       /* Selected face glow (pink) */

/* CAD Default */
--face-default: #90a4ae;       /* Neutral gray for uncolored faces */
--face-no-tol:  #374151;       /* Faces without tolerance data */
```

### Typography
```css
font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;

/* Brand */
.scribe-brand {
    font-weight: 800;
    letter-spacing: -0.02em;
    font-size: 1.25rem;
    color: var(--accent-blue);
    text-shadow: 0 0 12px var(--accent-glow);
}

/* Subtitle */
.scribe-subtitle {
    font-weight: 400;
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
}

/* Section Headers */
h2 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
h3 { font-size: 13px; font-weight: 700; }
h4 { font-size: 11px; color: var(--text-secondary); }
```

### Component Styles
- **Buttons**: `background: #374151`, `border: 1px solid #4b5563`, rounded 4px, hover → blue border
- **Inputs**: Dark backgrounds, subtle borders, focus → blue glow
- **Panels**: `background: var(--bg-panel)`, collapsible with chevron icons
- **Modals**: Centered, semi-transparent backdrop, clean headers with × close button
- **Sliders**: Dual-thumb range sliders for tolerance bands
- **Color Pickers**: Native `<input type="color">` with custom styling

---

## 📐 PAGE LAYOUT

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER (Top Menu Bar)                                                       │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ SCRIBE  "like PDFs for CAD"            [Import] [Export]         UUID   ││
│ └─────────────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────┐                                           ┌───┐───────────┐ │
│ │ LEFT PANEL  │                                           │ T │ RIGHT PNL │ │
│ │ (Hidden)    │                                           │ A │ (Props)   │ │
│ │             │         ┌─────────────────────┐           │ B │           │ │
│ │             │         │                     │           │ S │ Face Props│ │
│ │             │         │   3D VIEWPORT       │           │   │ - ID, Type│ │
│ │             │         │   (Three.js)        │           │   │ - Color   │ │
│ │             │         │                     │           │   │           │ │
│ │             │         │                     │           │   │ Threading │ │
│ │             │         │      [F][B][R]      │           │   │           │ │
│ │             │         │      [L][T][Bo]     │           │   │ Tolerance │ │
│ │ ┌─────────┐ │         │      [Iso]          │           │   │           │ │
│ │ │Console  │ │         └─────────────────────┘           │   │           │ │
│ │ │ > Log   │ │                                           │   │           │ │
│ │ └─────────┘ │                                           │   │           │ │
│ └─────────────┘                                           └───┴───────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Panel Behavior
- **Left Panel**: Fixed tools (Import, Export), console at bottom, collapsible via pin icon
- **Right Panel**: Context-sensitive, shows face properties when face selected, heat map settings when active, hole wizard when triggered
- **Both panels**: Collapsible with chevron, mouse events blocked from propagating to 3D viewport

---

## 🖱️ INTERACTION CONTROLS

### Mouse Controls
| Action | Input |
|--------|-------|
| **Orbit** | Left-drag |
| **Pan** | Right-drag |
| **Zoom** | Scroll wheel (zoom-to-cursor) |
| **Select Face** | Click |
| **Multi-select** | Shift+Click or Ctrl+Click |
| **Deselect All** | Escape key or double-click background |

### View Controls
### View Controls
- **Quick View Buttons**: Floating bar at bottom-center of viewport (F/B/L/R/T/Bo/Iso) — always visible.
- **Default View**: Isometric from front-left-bottom `(-1, -1, 1)` with Z-up.

### Camera
- **Type**: Orthographic (CAD-standard)
- **Rotation**: ArcballControls with damping (0.25) for fluid feel
- **Zoom**: Preserves cursor position (zoom-to-cursor), buttery smooth after pan (no jerking)

---

## 🔧 FEATURE SPECIFICATIONS

### 1. STEP File Import
```
/upload [POST] → multipart/form-data
  - Accepts: .step, .stp files
  - Returns: { faces: [...], uuid: "...", filename: "..." }
  - Redirects to: /view/{uuid}
```
- Drag-and-drop zone with upload icon
- Shows "Processing..." spinner during tessellation
- Auto-loads `tests/sample.STEP` on first boot

### 2. Face Selection & Properties
- Click face → highlight with pulsing pink glow (`#ec4899`)
- Pulse animation: subtle magnitude, moderate speed
- Right panel shows:
  - Face ID (hash-based)
  - Surface Type (Plane, Cylinder, Cone, Sphere, BSpline, Other)
  - Area (in²)
  - Color picker (surface color, not selection overlay)
  - Threading metadata dropdowns
  - Tolerance metadata dropdowns

### 3. Threading Metadata
```javascript
threadTypes: ["UNC", "UNF", "Metric Coarse", "Metric Fine", "Helicoil", "Keensert"]
threadSizes: {
  "UNC": ["#2-56", "#4-40", "#6-32", "#8-32", "#10-24", "#10-32", "1/4-20", "5/16-18", "3/8-16", "1/2-13"],
  "UNF": ["#4-48", "#6-40", "#8-36", "#10-32", "1/4-28", "5/16-24", "3/8-24", "1/2-20"],
  "Metric Coarse": ["M3x0.5", "M4x0.7", "M5x0.8", "M6x1", "M8x1.25", "M10x1.5", "M12x1.75"],
  "Metric Fine": ["M6x0.5", "M8x0.75", "M10x1", "M12x1.25"],
  // ... helicoil, keensert variants
}
```

### 4. Tolerance Metadata
```javascript
toleranceTypes: ["None", "Linear +/-", "Limit", "H7 (Hole)", "H8 (Hole)", "g6 (Shaft)", 
                 "Flatness", "Parallelism", "Perpendicularity", "Position", "Concentricity", "Custom"]

// Values are inch-based machining tolerances (0.0005" to 0.030")
toleranceValues: [
    "None",
    "+/- 0.0005", "+/- 0.001", "+/- 0.002", "+/- 0.003", "+/- 0.005",
    "+/- 0.010", "+/- 0.015", "+/- 0.020", "+/- 0.030",
    "+0.000/-0.001", "+0.001/-0.000", "+0.000/-0.005", "+0.005/-0.000",
    "0.001 TIR", "0.002 TIR", "0.005 TIR", "0.010 TIR"
]
```

### 5. Heat Map Mode
- Toggle via vertical tab or toolbar
- Right panel shows **Tolerances**:
  - **Checkboxes**: Filter by type (Linear ±, Limit, GD&T, Fits)
  - **Heat Map Groups**: Expanding lists of faces by tolerance type
  - **Coloring**: 
    - **Tight Tolerances** (≤ 0.005"): **Red** `#f44336` (Configurable)
    - **Loose Tolerances** (> 0.005"): **Gray** `#b0b0b0` (Configurable)
    - **No Tolerance**: Light Gray `ghosted`
  - **Legend**: Visual key for Tight vs Loose

### 6. Hole Wizard
- Toggle via vertical tab or toolbar
- Right panel shows **Hole Wizard**:
  - **Thread Groups**: Expandable groups by thread type (e.g. "UNC 1/4-20")
    - Populated from **metadata** (user-defined), not just geometry
    - **Color Picker**: Assign distinct color to each thread group
    - **Visibility Eye**: Toggle group visibility
    - **Delete**: Remove thread data from group
  - **Cylindrical Faces**: Count of detected cylinders (unthreaded)

### 7. Lighting System
- Modal triggered by toolbar button
- Settings:
  - **Preset**: Standard (3-Point), Flat (Even), Dramatic (High Contrast)
  - **Ambient Intensity**: 0-2 (default: 0.4)
  - **Key Light**: 0-3 (default: 1.0)
  - **Fill Light**: 0-2 (default: 0.5)
  - **Back Light**: 0-2 (default: 0.5)

### 8. Export
- Single "Export" button (not "Export Colored STEP")
- Exports STEP file with:
  - Face colors embedded via XDE styled-items
  - Metadata embedded via THREE strategies:
    1. PROPERTY_DEFINITION on PRODUCT_DEFINITION (SolidWorks-compatible)
    2. DESCRIPTIVE_REPRESENTATION_ITEM (universal CAD compatibility)
    3. Comment block fallback (fast for SCRIBE-to-SCRIBE)
- Filename: `{original}_scribe.step`

---

## 💾 DATABASE SCHEMA (SQLite)

### `faces` Table
```sql
CREATE TABLE faces (
    id INTEGER PRIMARY KEY,
    face_hash TEXT UNIQUE NOT NULL,      -- 16-char hex from geometry fingerprint
    meta TEXT DEFAULT '{}',              -- JSON: {color, thread, tolerance, ...}
    
    -- Raw fingerprint values for fuzzy matching
    surf_type TEXT,
    cx REAL, cy REAL, cz REAL,           -- Centroid
    area REAL,
    dx REAL, dy REAL, dz REAL,           -- Bounding box dimensions
    n_edges INTEGER,
    n_verts INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_faces_hash ON faces(face_hash);
```

### Face Fingerprinting Algorithm
1. Extract geometry: surface type, centroid, area, bbox dimensions, edge/vertex counts
2. Hash with 3-decimal rounding for kernel-consistent matching
3. Fuzzy matching tolerances:
   - Position: 10 microns
   - Area: 0.1 mm²
   - Dimensions: 10 microns
4. Topology (surf_type, n_edges, n_verts) must match exactly

---

## 🌐 API ENDPOINTS

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Serve main app (auto-loads sample.STEP) |
| GET | `/view/{uuid}` | Load model by UUID |
| POST | `/upload` | Upload STEP file |
| GET | `/model/{uuid}` | Get face data for model |
| POST | `/set_color` | Set face color(s) |
| POST | `/set_thread` | Set threading metadata |
| GET | `/thread_options` | Get thread dropdown options |
| GET | `/holes` | Get hole analysis data |
| POST | `/export` | Export annotated STEP |
| POST | `/test_cube` | Boot test (internal) |
| GET | `/test_sample` | Load sample.STEP (internal) |

---

## 🚀 DEPLOYMENT (GCP Cloud Run)

### Dockerfile
```dockerfile
FROM python:3.9-slim
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

## ⚡ IMPLEMENTATION PRIORITIES

### Phase 1: Core Viewer
1. Flask app skeleton with STEP upload route
2. CadQuery/OCP tessellation with face extraction
3. Three.js viewer with orthographic camera
4. Face picking and selection highlight
5. Basic left/right panel layout

### Phase 2: Metadata System
1. SQLite face fingerprinting database
2. Color editing with live preview
3. Threading dropdowns with save-to-DB
4. Tolerance dropdowns with save-to-DB
5. Console logging panel

### Phase 3: Advanced Features
1. Heat map mode with dual sliders and color pickers
2. Hole wizard with diameter grouping
3. Lighting modal with presets
4. View cube / Quick view buttons
5. STEP export with embedded metadata

### Phase 4: Polish
1. Panel collapse/expand with chevrons
2. Multi-select with Shift/Ctrl
3. Zoom-to-cursor behavior
4. Selection pulse animation
5. Edge rendering (35% thicker than default)

---

## 🚫 EXCLUDED FEATURES (Explicitly Removed)

- ❌ Grid dots display
- ❌ Axis display (hidden by default)
- ❌ Snap-to-grid
- ❌ Tolerances button/modal (removed)
- ❌ Navigation help text
- ❌ Perspective camera (ortho only)
- ❌ View Cube (replaced by floating viewport buttons)

---

## 📝 DESIGN PRINCIPLES

1. **CAD-First UX**: Orthographic views, arcball rotation, zoom-to-cursor — like SolidWorks/Fusion
2. **Metadata Survives**: Annotations embed in STEP file itself, not just overlay
3. **Zero Dependencies Frontend**: Vanilla JS/CSS, no React/Vue/Tailwind bloat
4. **Dark Professional Aesthetic**: Clean, modern, focused on the 3D content
5. **Instant Feedback**: Console logs all actions, DB saves confirmed
6. **Machinist Units**: Default to inches, tolerance bands reflect machining reality

---

## 🧪 TESTING REQUIREMENTS

1. **Boot Test**: Auto-load `tests/sample.STEP` on first visit
2. **Face Selection**: Click → pink glow, multi-select with Shift
3. **Color Persistence**: Set color → refresh → color persists (DB + STEP export)
4. **Heat Map**: Enable → sliders affect face colors → disable → colors restore
5. **Hole Detection**: Cylindrical faces grouped by diameter (via geometry analysis) and Thread Type (via metadata)
6. **Export Round-Trip**: Upload → annotate → export → re-upload → annotations preserved
7. **Automated Suite**: `tests/test_hole_tolerance_suite.py` verifies metadata persistence using `tests/sample.STEP`

---

> **Build this with the precision of a machinist and the elegance of a Swiss watch.** ⚙️
