# -*- coding: utf-8 -*-
"""STEP（.step/.stp）→ 多视角 PNG + 可选装配树 / figure_plan 种子。

**默认关闭**：必须显式传入 ``--enable-step-parse``（或环境变量
``PATENT_SKILL_STEP_PARSE=1``），且依赖需用户确认后安装：

  pip install -r tools/shared/requirements-step.txt

示例：

  python tools/shared/step_to_views.py --check-deps
  python tools/shared/step_to_views.py --enable-step-parse -i model.step -o outputs/case/cad_views
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SHARED = Path(__file__).resolve().parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from cad_formats import is_step  # noqa: E402

# 标准工程视图：名称 → CadQuery SVG projectionDir
DEFAULT_VIEWS: dict[str, tuple[float, float, float]] = {
    "iso": (1.0, 1.0, 1.0),
    "front": (0.0, -1.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "right": (1.0, 0.0, 0.0),
}

ENABLE_ENV = "PATENT_SKILL_STEP_PARSE"


def _cairosvg_usable() -> tuple[bool, str]:
    """cairosvg 依赖系统 Cairo；Windows 常缺 DLL，此时不算硬失败。"""
    try:
        import cairosvg  # noqa: F401

        # 触发一次底层 cairo 加载（仅 import 有时不够）
        getattr(cairosvg, "svg2png")
        import cairocffi  # type: ignore  # noqa: F401

        return True, getattr(cairosvg, "__version__", "unknown")
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _matplotlib_usable() -> tuple[bool, str]:
    try:
        import matplotlib  # noqa: F401

        return True, getattr(matplotlib, "__version__", "unknown")
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def deps_status() -> dict[str, Any]:
    missing: list[str] = []
    versions: dict[str, str] = {}
    hints: list[str] = []
    try:
        import cadquery as cq  # noqa: F401

        versions["cadquery"] = getattr(cq, "__version__", "unknown")
    except Exception as e:  # noqa: BLE001 — 探测用
        missing.append(f"cadquery ({e})")

    cairo_ok, cairo_info = _cairosvg_usable()
    if cairo_ok:
        versions["cairosvg"] = cairo_info
    else:
        hints.append(f"cairosvg/Cairo 不可用，将尝试 matplotlib 回退: {cairo_info}")

    mpl_ok, mpl_info = _matplotlib_usable()
    if mpl_ok:
        versions["matplotlib"] = mpl_info
    elif not cairo_ok:
        missing.append(
            f"PNG 后端缺失：需 cairosvg(+系统 Cairo) 或 matplotlib；cairosvg={cairo_info}; matplotlib={mpl_info}"
        )

    return {
        "ok": not missing,
        "missing": missing,
        "versions": versions,
        "hints": hints,
        "install": "pip install -r tools/shared/requirements-step.txt",
    }


def parse_enabled(cli_flag: bool) -> bool:
    if cli_flag:
        return True
    return os.environ.get(ENABLE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_stem(path: Path) -> str:
    s = path.stem
    out = "".join(c if c.isalnum() or c in "-_" else "_" for c in s)
    return (out or "model")[:80]


def extract_assembly_tree(step_path: Path) -> dict[str, Any]:
    """尽力从 STEP 取装配标签；失败则回退为单节点 + solids 计数。"""
    tree: dict[str, Any] = {
        "source": str(step_path.resolve()),
        "parts": [],
        "uncertain": [],
        "method": "unknown",
    }
    try:
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDF import TDF_Label, TDF_LabelSequence
        from OCP.TDocStd import TDocStd_Document
        from OCP.XCAFApp import XCAFApp_Application
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
    except Exception as e:  # noqa: BLE001
        tree["uncertain"].append(f"OCP/XCAF 不可用: {e}")
        return _fallback_solids_tree(step_path, tree)

    try:
        app = XCAFApp_Application.GetApplication_s()
        doc = TDocStd_Document(TCollection_ExtendedString("MDTV-CAF"))
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        status = reader.ReadFile(str(step_path))
        if status != IFSelect_RetDone:
            tree["uncertain"].append("STEPCAF ReadFile 未成功")
            return _fallback_solids_tree(step_path, tree)
        if not reader.Transfer(doc):
            tree["uncertain"].append("STEPCAF Transfer 失败")
            return _fallback_solids_tree(step_path, tree)

        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        labels = TDF_LabelSequence()
        shape_tool.GetFreeShapes(labels)
        parts: list[dict[str, Any]] = []

        def _label_name(lab: TDF_Label) -> str:
            attr = TDataStd_Name()
            if lab.FindAttribute(TDataStd_Name.GetID_s(), attr):
                return attr.Get().ToExtString()
            return ""

        for i in range(1, labels.Length() + 1):
            lab = labels.Value(i)
            name = _label_name(lab) or f"Shape_{i}"
            parts.append({"id": str(i), "name": name, "label_path": name})
            children = TDF_LabelSequence()
            if shape_tool.GetComponents(lab, children):
                for j in range(1, children.Length() + 1):
                    clab = children.Value(j)
                    cname = _label_name(clab) or f"{name}_child_{j}"
                    parts.append(
                        {
                            "id": f"{i}.{j}",
                            "name": cname,
                            "parent": str(i),
                            "label_path": f"{name}/{cname}",
                        }
                    )

        tree["parts"] = parts or [{"id": "1", "name": step_path.stem, "label_path": step_path.stem}]
        tree["method"] = "xcaf"
        if not parts:
            tree["uncertain"].append("XCAF 未枚举到子件，仅有自由形状根")
        return tree
    except Exception as e:  # noqa: BLE001
        tree["uncertain"].append(f"XCAF 解析异常: {e}")
        return _fallback_solids_tree(step_path, tree)


def _fallback_solids_tree(step_path: Path, tree: dict[str, Any]) -> dict[str, Any]:
    try:
        import cadquery as cq
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer

        shape = cq.importers.importStep(str(step_path))
        wrapped = shape.val().wrapped
        exp = TopExp_Explorer(wrapped, TopAbs_SOLID)
        n = 0
        parts = []
        while exp.More():
            n += 1
            parts.append({"id": str(n), "name": f"Solid_{n}", "label_path": f"Solid_{n}"})
            exp.Next()
        if not parts:
            parts = [{"id": "1", "name": step_path.stem, "label_path": step_path.stem}]
            tree["uncertain"].append("未拆出 SOLID，按整模一件处理")
        tree["parts"] = parts
        tree["method"] = "solid_count"
        tree["solid_count"] = n
    except Exception as e:  # noqa: BLE001
        tree["parts"] = [{"id": "1", "name": step_path.stem, "label_path": step_path.stem}]
        tree["method"] = "stem_only"
        tree["uncertain"].append(f"无法计数 SOLID: {e}")
    return tree


def _project_point(
    p: tuple[float, float, float],
    direction: tuple[float, float, float],
) -> tuple[float, float]:
    """把 3D 点投影到以 direction 为视线的正交平面（构造简易相机基）。"""
    import math

    dx, dy, dz = direction
    norm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    zx, zy, zz = dx / norm, dy / norm, dz / norm
    # up ≈ Z，退化时用 Y
    ux, uy, uz = 0.0, 0.0, 1.0
    if abs(zx * ux + zy * uy + zz * uz) > 0.9:
        ux, uy, uz = 0.0, 1.0, 0.0
    # right = up × forward? 用 forward × up 得 right
    rx = zy * uz - zz * uy
    ry = zz * ux - zx * uz
    rz = zx * uy - zy * ux
    rn = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    rx, ry, rz = rx / rn, ry / rn, rz / rn
    # up' = forward × right
    ux = zy * rz - zz * ry
    uy = zz * rx - zx * rz
    uz = zx * ry - zy * rx
    x, y, z = p
    u = x * rx + y * ry + z * rz
    v = x * ux + y * uy + z * uz
    return u, v


def _svg_to_png_cairo(svg_path: Path, png_path: Path) -> None:
    import cairosvg

    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


def _shape_to_png_matplotlib(
    shape: Any,
    direction: tuple[float, float, float],
    png_path: Path,
    *,
    size: int = 900,
) -> None:
    """无系统 Cairo 时：镶嵌三角面 → 正交投影线框 PNG（matplotlib Agg）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    solid = shape.val()
    # CadQuery Shape.tessellate → (Vector list, triangle index list)
    verts, tris = solid.tessellate(0.35)
    pts = [(float(v.x), float(v.y), float(v.z)) for v in verts]
    proj = [_project_point(p, direction) for p in pts]
    edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    for a, b, c in tris:
        tri = (a, b, c)
        for i in range(3):
            i0, i1 = tri[i], tri[(i + 1) % 3]
            p0, p1 = proj[i0], proj[i1]
            key = (p0, p1) if p0 <= p1 else (p1, p0)
            edges.add(key)
    segs = list(edges)
    fig, ax = plt.subplots(figsize=(size / 100, size / 100), dpi=100)
    if segs:
        ax.add_collection(LineCollection(segs, colors="black", linewidths=0.6))
        xs = [p[0] for s in segs for p in s]
        ys = [p[1] for s in segs for p in s]
        pad_x = (max(xs) - min(xs)) * 0.08 + 1e-3
        pad_y = (max(ys) - min(ys)) * 0.08 + 1e-3
        ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
        ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout(pad=0.1)
    fig.savefig(png_path, dpi=100, facecolor="white")
    plt.close(fig)


def render_views(
    step_path: Path,
    out_dir: Path,
    *,
    views: dict[str, tuple[float, float, float]] | None = None,
    stem: str | None = None,
) -> list[dict[str, Any]]:
    import cadquery as cq

    views = views or DEFAULT_VIEWS
    stem = stem or _safe_stem(step_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    shape = cq.importers.importStep(str(step_path))
    cairo_ok, _ = _cairosvg_usable()
    results: list[dict[str, Any]] = []

    for name, direction in views.items():
        svg_path = out_dir / f"{stem}_{name}.svg"
        png_path = out_dir / f"{stem}_{name}.png"
        cq.exporters.export(
            shape,
            str(svg_path),
            cq.exporters.ExportTypes.SVG,
            opt={
                "projectionDir": direction,
                "showAxes": False,
                "showHidden": False,
                "strokeWidth": 0.2,
            },
        )
        png_backend = "cairosvg"
        try:
            if cairo_ok:
                _svg_to_png_cairo(svg_path, png_path)
            else:
                raise RuntimeError("cairosvg unavailable")
        except Exception:
            _shape_to_png_matplotlib(shape, direction, png_path)
            png_backend = "matplotlib_tessellate"
        role = "assembly" if name == "iso" else "ortho"
        results.append(
            {
                "name": name,
                "role": role,
                "png": str(png_path.resolve()),
                "svg": str(svg_path.resolve()),
                "projectionDir": list(direction),
                "png_backend": png_backend,
            }
        )
    return results


def build_figure_plan_seed(
    *,
    view_records: list[dict[str, Any]],
    out_path: Path,
    theme_summary: str,
    schema_ref: str = "structure_schema.yaml",
    patent_type: str = "utility_model",
) -> dict[str, Any]:
    """预填 assembly + alternate_view 的 figure_plan 草稿（供 Agent 审改后定稿）。"""
    figures: list[dict[str, Any]] = []
    iso_fig: int | None = None
    fig_no = 0
    for rec in view_records:
        fig_no += 1
        role = rec.get("role") or ("assembly" if rec["name"] == "iso" else "ortho")
        relates: list[dict[str, Any]] = []
        if role != "assembly" and iso_fig is not None:
            relates.append(
                {
                    "fig": iso_fig,
                    "relation": "alternate_view",
                    "note": f"与图{iso_fig}同模型另一投影（STEP 自动）",
                }
            )
        entry = {
            "fig": fig_no,
            "role": role if role in {"assembly", "ortho", "perspective", "detail"} else "ortho",
            "path": rec["png"],
            "covers": [],
            "kind": "cad",
            "score": 92 if role == "assembly" else 80,
            "use_in_disclosure": True,
            "reason": f"STEP 自动视图 {rec['name']}",
            "relates_to": relates,
        }
        if role == "assembly" and iso_fig is None:
            iso_fig = fig_no
            entry["role"] = "assembly"
        figures.append(entry)

    plan = {
        "$schema": "figure_plan",
        "version": 1,
        "patent_type": patent_type,
        "theme_summary": theme_summary or "STEP 自动多视角（待人工确认主题）",
        "schema_ref": schema_ref,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "figures": figures,
        "notes": [
            "本文件由 step_to_views.py 生成，属草稿；填 StructureSchema 后请重评 covers / score / 入文选择。",
            "局部细节图需另增材料或人工指定 crop；自动视图仅含投影。",
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_yaml(out_path, plan)
    return plan


def build_structure_seed(tree: dict[str, Any], out_path: Path) -> dict[str, Any]:
    parts = []
    for p in tree.get("parts") or []:
        parts.append(
            {
                "id": str(p.get("id", "")),
                "name": p.get("name") or "",
                "shape": "unknown",
                "material_hint": "unknown",
            }
        )
    if not parts:
        parts = [{"id": "1", "name": "unknown", "shape": "unknown", "material_hint": "unknown"}]
    seed = {
        "$schema": "structure.schema",
        "version": 1,
        "mode": "disclosure",
        "source_images": [],
        "parts": parts,
        "relations": [],
        "spatial": [],
        "function_of_structure": [],
        "delta_hypothesis": [],
        "uncertain": list(tree.get("uncertain") or [])
        + [
            "装配树来自 STEP 自动解析，件名可能为特征名/空名；须对照视图修订",
            "连接关系未从 STEP 推断，须识图后填写 relations",
        ],
        "not_utility_model_signals": [],
        "cad_assembly_method": tree.get("method"),
    }
    _write_yaml(out_path, seed)
    return seed


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore

        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except Exception:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            # 无 PyYAML 时仍用请求的文件名，内容为 JSON（Agent 可读）
            pass


def run_convert(
    step_path: Path,
    out_dir: Path,
    *,
    write_assembly: bool = True,
    write_figure_plan: bool = True,
    write_structure_seed: bool = True,
    theme_summary: str = "",
) -> dict[str, Any]:
    if not step_path.is_file():
        raise FileNotFoundError(step_path)
    if not is_step(step_path):
        raise ValueError(f"不是 .step/.stp: {step_path}")

    status = deps_status()
    if not status["ok"]:
        raise RuntimeError(
            "缺少 STEP 解析依赖: "
            + "; ".join(status["missing"])
            + f"。请先: {status['install']}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(step_path)
    views_dir = out_dir / "views"
    view_records = render_views(step_path, views_dir, stem=stem)

    result: dict[str, Any] = {
        "step": str(step_path.resolve()),
        "out_dir": str(out_dir.resolve()),
        "views": view_records,
        "artifacts": {},
    }

    tree = extract_assembly_tree(step_path)
    if write_assembly:
        asm_path = out_dir / "assembly_tree.yaml"
        _write_yaml(asm_path, tree)
        result["artifacts"]["assembly_tree"] = str(asm_path.resolve())
        result["assembly_tree"] = tree

    if write_structure_seed:
        struct_path = out_dir / "structure_schema.seed.yaml"
        build_structure_seed(tree, struct_path)
        result["artifacts"]["structure_schema_seed"] = str(struct_path.resolve())

    if write_figure_plan:
        fp_path = out_dir / "figure_plan.seed.yaml"
        build_figure_plan_seed(
            view_records=view_records,
            out_path=fp_path,
            theme_summary=theme_summary or f"STEP:{step_path.name}",
        )
        result["artifacts"]["figure_plan_seed"] = str(fp_path.resolve())

    manifest = out_dir / "step_to_views_manifest.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["artifacts"]["manifest"] = str(manifest.resolve())
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="STEP → 多视角 PNG + 装配树/figure_plan 种子（默认关闭，需 --enable-step-parse）"
    )
    p.add_argument("--check-deps", action="store_true", help="仅检查依赖，不转换")
    p.add_argument(
        "--enable-step-parse",
        action="store_true",
        help="显式开启（或设环境变量 PATENT_SKILL_STEP_PARSE=1）",
    )
    p.add_argument("-i", "--input", help="输入 .step / .stp")
    p.add_argument("-o", "--out-dir", help="输出目录（建议 outputs/{案件}/cad_views/）")
    p.add_argument("--theme", default="", help="figure_plan theme_summary")
    p.add_argument("--no-assembly", action="store_true")
    p.add_argument("--no-figure-plan", action="store_true")
    p.add_argument("--no-structure-seed", action="store_true")
    args = p.parse_args(argv)

    if args.check_deps:
        st = deps_status()
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0 if st["ok"] else 2

    if not parse_enabled(args.enable_step_parse):
        print(
            json.dumps(
                {
                    "error": "step_parse_disabled",
                    "message": (
                        "STEP 解析默认关闭。请经用户确认后使用 --enable-step-parse，"
                        f"或设置 {ENABLE_ENV}=1。"
                    ),
                    "install": "pip install -r tools/shared/requirements-step.txt",
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3

    if not args.input or not args.out_dir:
        p.error("转换模式需要 -i/--input 与 -o/--out-dir（或改用 --check-deps）")

    try:
        result = run_convert(
            Path(args.input),
            Path(args.out_dir),
            write_assembly=not args.no_assembly,
            write_figure_plan=not args.no_figure_plan,
            write_structure_seed=not args.no_structure_seed,
            theme_summary=args.theme,
        )
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": type(e).__name__, "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"STEP_TO_VIEWS_OK: {result['out_dir']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
