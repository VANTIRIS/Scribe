# SCRIBE - Technical Documentation & Codebase Overview

> **Context for LLMs**: This repository is a lightweight, browser-based STEP file viewer and annotation tool ("PDF for CAD"). It uses a Python Flask backend with CadQuery/OCP for geometry processing and a Three.js frontend for rendering.
> 
> **Core Philosophy**: Treat STEP files as authoritative documents. Metadata (tolerances, threads, colors) is injected directly into the STEP file structures or persisted via sidecar SQLite DB, keyed by geometry hashes.

---

## 📂 File Structure & Logic Map

```text
/
├── app.py                  # MAIN BACKEND ENTRYPOINT
│   ├── [Routes]            # /upload, /save_metadata, /test_sample
│   ├── [Logic]             # load_step_xcaf(), export_step_xcaf()
│   └── [DB]                # SQLite connection & schema (face_metadata table)
├── requirements.txt        # Python dependencies (Flash, CadQuery, OCP, etc.)
├── static/
│   ├── js/
│   │   ├── viewer.js       # MAIN FRONTEND LOGIC
│   │   │   ├── [Init]      # Scene setup, Event listeners
│   │   │   ├── [Core]      # loadModel(), buildScene(), fitCamera()
│   │   │   ├── [Tools]     # Raycasting, Heat Map, Hole Wizard
│   │   │   └── [UI]        # Panel toggles, DOM updates
│   │   └── three.min.js    # Three.js library
│   └── css/
│       └── style.css       # UI Styling (Dark mode, absolute positioning)
├── templates/
│   └── index.html          # Single Page Application (SPA) container
├── tests/
│   └── sample.STEP         # Default loaded model
└── metadata.db             # Local SQLite DB (generated at runtime)
```

---

## 🧠 Core Logic & Systems

### 1. Backend (`app.py`)
**Framework**: Flask + Gunicorn
**Geometry Kernel**: Open Cascade (OCCT) via `cadquery` & `OCP`.

#### Key Functions
*   **`load_step_xcaf(path)`**: 
    *   Reads STEP using `STEPCAFControl_Reader`.
    *   Iterates topological faces (`TopExp_Explorer`).
    *   **Hashing**: Generates a stable geometry hash for each face (Center of Mass + Area + Normal) to link metadata even if file is re-exported.
    *   **Metadata Recovery**: Checks `metadata.db` AND internal `XCAF` labels for colors/names.
    *   **Tessellation**: Converts BRep to Mesh (`BRepMesh_IncrementalMesh`) for Three.js.
*   **`export_step_with_color(faces, path)`**:
    *   Reconstructs a generic compound from modified faces.
    *   **Injection**: Uses `XCAFDoc_ColorTool` to embed user-assigned colors directly into the STEP file structure.
    *   **Attributes**: Writes metadata (Thread, Tolerance) as `TDataStd_Name` or `User Data` labels in the XCAF tree.

### 2. Frontend (`viewer.js` + `index.html`)
**Framework**: Vanilla JS + Three.js (WebGL)

#### Rendering Pipeline
1.  **`loadModel()`**: Fetches JSON payload from `/upload` (Vertices, Normals, Indices, Metadata).
2.  **`buildScene()`**: 
    *   Creates `THREE.BufferGeometry` for each face.
    *   Assigns `userData` (FaceID, Thread info, Tolerance) to each mesh.
    *   Adds edges (`THREE.LineSegments`) for visual clarity.
3.  **`fitCameraToGroup()`**: Calculates bounding box and positions camera at **Isometric (-1, -1, 1)** default.

#### Interaction Logic
*   **Arcball Controls**: Custom implementation using `ArcballControls.js` (or similar logic) for "tumbling" rotation.
*   **Raycasting (`onPointerUp`)**:
    *   Casts ray from mouse coords.
    *   **Selection**: Highlights face (Emissive material), populates "Right Panel".
*   **View Switching**:
    *   **Floating Buttons**: Camera moves to fixed vector (e.g., `(0, 1, 0)` for Top) & `lookAt(center)`.

### 3. Feature: Tolerance Heat Map
**Logic Location**: `applyHeatMap()` in `viewer.js`
*   **Input**: `faces` array with `tolerance` metadata.
*   **Colors**:
    *   **Tight** (<= 0.005"): Lerps to **Red** (configurable).
    *   **Loose** (> 0.005"): Lerps to **Gray** (configurable).
    *   **None**: Sets material to `transparent/ghosted`.
*   **Filtering**: Checks checkboxes (Linear, GD&T, etc.) and hides meshes that don't match.

### 4. Feature: Hole Wizard
**Logic Location**: `loadHoleManager()` in `viewer.js`
*   **Grouping**: Iterates all faces.
    *   Checks `userData.thread` (e.g., "UNC 1/4-20").
    *   Groups matching faces into a "Thread Group".
*   **Interaction**: Default view hides *everything* except the hole faces.
*   **Coloring**: User can assign a hex color to a "Thread Group". This overrides the face's material color in the `Three.js` scene.

---

## 💾 Data Schema (`metadata.db`)

**Table**: `face_metadata`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER | Primary Key |
| `file_hash` | TEXT | Hash of the parent STEP file content |
| `face_id` | INTEGER | Index of the face in the STEP topology |
| `geom_hash` | TEXT | **Critical**: Geometric fingerprint (centroid+area) for robust matching |
| `color` | TEXT | Hex code (`#ff0000`) |
| `thread` | JSON | `{type: "UNC", size: "1/4-20", ...}` |
| `tolerance` | JSON | `{type: "linear", value: 0.005, ...}` |

---

## 🔄 API Endpoints

| Method | Endpoint | Payload | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/upload` | `multipart/form-data` | Uploads STEP, processes to JSON mesh + meta. |
| `GET` | `/test_sample`| `None` | Auto-loads `tests/sample.STEP`. |
| `POST` | `/save_metadata` | JSON `{face_id, data...}` | Updates DB and in-memory cache for a face. |
| `POST` | `/set_tolerance` | JSON `{updates: []}` | Batch updates tolerances (Heat Map). |
| `GET` | `/export_step/UUID` | `None` | Triggers generic compound rebuild + XCAF color injection -> Download. |
