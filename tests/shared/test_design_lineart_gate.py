# -*- coding: utf-8 -*-
"""design_lineart_gate：默认关、无图拒绝、有图可出 jobs。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "tools" / "shared"
sys.path.insert(0, str(SHARED))

from design_lineart_gate import (  # noqa: E402
    CONFIRM_ZH,
    build_jobs,
    parse_enabled,
    run_check,
    validate_brief,
)


class TestDesignLineartGate(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(parse_enabled(False))
        self.assertTrue(parse_enabled(True))
        self.assertIn("是", CONFIRM_ZH)

    def test_check_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            report = run_check(Path(td), enabled=False)
            self.assertFalse(report["ok"])
            self.assertTrue(any("默认关闭" in e for e in report["errors"]))

    def test_no_images_forbid(self):
        with tempfile.TemporaryDirectory() as td:
            case = Path(td)
            (case / "figure_plan.yaml").write_text(
                "patent_type: design\nfigures: []\n",
                encoding="utf-8",
            )
            report = run_check(case, enabled=True)
            self.assertFalse(report["ok"])
            self.assertTrue(any("禁止" in e or "无可用" in e or "缺少" in e for e in report["errors"]))

    def test_validate_and_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            case = Path(td)
            img = case / "p.jpg"
            img.write_bytes(b"\xff\xd8\xff\xd9")
            brief = {
                "enabled": True,
                "patent_type": "design",
                "overall_shape": "折臂台灯",
                "design_points": ["弯月灯头"],
                "views": [
                    {
                        "view_name": "立体图",
                        "source_paths": [str(img)],
                        "source_figs": [1],
                        "relates_hint": [{"fig": 1, "relation": "same_state"}],
                        "lineart_goal": "整体轮廓",
                        "gen_prompt": "",
                        "output_path": "lineart_assist/stereo_lineart.png",
                    }
                ],
            }
            self.assertEqual(validate_brief(brief, case), [])
            jobs = build_jobs(brief, case)
            self.assertEqual(len(jobs), 1)
            self.assertTrue(jobs[0]["forbid_text_only"])
            self.assertEqual(jobs[0]["reference_images"], [str(img.resolve())])
            self.assertEqual(jobs[0]["source_paths"], jobs[0]["reference_images"])
            self.assertIn("line art", jobs[0]["gen_prompt"].lower())

            # full prepare path via files
            try:
                import yaml  # type: ignore

                (case / "design_lineart_brief.yaml").write_text(
                    yaml.safe_dump(brief, allow_unicode=True),
                    encoding="utf-8",
                )
            except Exception:
                (case / "design_lineart_brief.yaml").write_text(
                    json.dumps(brief, ensure_ascii=False),
                    encoding="utf-8",
                )
            (case / "figure_plan.yaml").write_text(
                f"patent_type: design\nfigures:\n  - fig: 1\n    path: {img.name}\n    use_in_disclosure: true\n",
                encoding="utf-8",
            )
            report = run_check(case, enabled=True)
            self.assertTrue(report["ok"], report)


if __name__ == "__main__":
    unittest.main()
