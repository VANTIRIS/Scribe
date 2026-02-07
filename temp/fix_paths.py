"""Fix paths in all test files after moving to tests/ directory."""
import os

TESTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")

for fname in os.listdir(TESTS_DIR):
    if not fname.endswith(".py"):
        continue
    fpath = os.path.join(TESTS_DIR, fname)
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        print(f"  Skipped (encoding): {fname}")
        continue

    original = content

    # Fix TEMP references
    content = content.replace(
        'TEMP = os.path.dirname(os.path.abspath(__file__))',
        'TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")',
    )
    content = content.replace(
        'TEMP = os.path.dirname(__file__)',
        'TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")',
    )

    # Fix SolidWorks cube path
    content = content.replace(
        r'SW_FILE = r"c:\repo_cad\cube export 4.STEP"',
        'SW_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "cube_solidworks.step")',
    )

    # Fix face_db sys.path insert (test_fingerprint_diff and test_color_roundtrip)
    content = content.replace(
        'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))',
        'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))',
    )

    if content != original:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Updated: {fname}")
    else:
        print(f"  Unchanged: {fname}")
