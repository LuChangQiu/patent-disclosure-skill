"""OMML 公式与 md_to_docx 双轨（OMML → PNG）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "tools" / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))


class MathToOmmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import latex2mathml  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("latex2mathml not installed")

    def test_latex_to_omml_has_omath(self):
        from lxml import etree
        from math_to_omml import latex_to_omml

        el = latex_to_omml(r"s = \alpha x + \beta y", display=True)
        s = etree.tostring(el, encoding="unicode")
        self.assertIn("oMath", s)

    def test_try_fails_gracefully(self):
        from math_to_omml import try_latex_to_omml

        # 极怪输入仍应返回 None 而非抛错
        self.assertIsNone(try_latex_to_omml(r"\unknownmacro{???{{{"))


class MdToDocxOmmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import latex2mathml  # noqa: F401
            from docx import Document  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("latex2mathml/python-docx missing")

    def test_block_equation_writes_omml(self):
        from md_to_docx import convert_md_to_docx

        md = "前文\n\n$$\ns = \\alpha x + \\beta y\n$$\n\n后文\n"
        doc = convert_md_to_docx(md, base_dir=None, prefer_omml=True)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "t.docx"
            doc.save(str(out))
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("word/document.xml").decode("utf-8")
        self.assertIn("oMath", xml)
        self.assertIn("oMathPara", xml)

    def test_no_omml_falls_back_without_crash(self):
        from md_to_docx import convert_md_to_docx

        md = "$$\na+b\n$$\n"
        doc = convert_md_to_docx(md, base_dir=None, prefer_omml=False)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "t.docx"
            doc.save(str(out))
            self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
