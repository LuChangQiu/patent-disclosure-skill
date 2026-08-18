# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "tools" / "shared"
sys.path.insert(0, str(SHARED))

from structure_callout_overlay import image_size, render_view, validate_manifest


# 1×1 白色 PNG。
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nE0AAAAASUVORK5CYII="
)


class TestStructureCalloutOverlay(unittest.TestCase):
    def test_validate_and_render_svg(self):
        with tempfile.TemporaryDirectory() as td:
            case = Path(td)
            (case / "lineart.png").write_bytes(PNG)
            manifest = {
                "version": 1,
                "coordinate_system": "normalized",
                "views": [
                    {
                        "image_path": "lineart.png",
                        "output_svg_path": "lineart_callouts.svg",
                        "callouts": [
                            {
                                "id": "1",
                                "name": "壳体",
                                "anchor": [0.65, 0.65],
                                "label": [0.85, 0.40],
                                "confidence": 0.95,
                            }
                        ],
                    }
                ],
            }
            structure = {"parts": [{"id": "1", "name": "壳体"}]}
            self.assertEqual(validate_manifest(manifest, case, structure=structure), [])
            self.assertEqual(image_size(case / "lineart.png"), (1, 1))
            output = render_view(manifest["views"][0], case)
            text = output.read_text(encoding="utf-8")
            self.assertIn('data-part-id="1"', text)
            self.assertIn("<path", text)
            self.assertIn(">1</text>", text)
            self.assertIn("data:image/png;base64,", text)

    def test_rejects_unknown_id_and_bad_coordinates(self):
        with tempfile.TemporaryDirectory() as td:
            case = Path(td)
            (case / "lineart.png").write_bytes(PNG)
            manifest = {
                "version": 1,
                "coordinate_system": "normalized",
                "views": [
                    {
                        "image_path": "lineart.png",
                        "output_svg_path": "out.svg",
                        "callouts": [
                            {
                                "id": "99",
                                "name": "未知",
                                "anchor": [1.2, 0.5],
                                "label": [0.5, 0.5],
                                "confidence": 0.4,
                            }
                        ],
                    }
                ],
            }
            errors = validate_manifest(
                manifest,
                case,
                structure={"parts": [{"id": "1", "name": "壳体"}]},
            )
            self.assertTrue(any("99" in error for error in errors))
            self.assertTrue(any("超出" in error for error in errors))
            self.assertTrue(any("置信度" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
