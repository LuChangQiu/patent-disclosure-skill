# -*- coding: utf-8 -*-
"""外观辅助线稿门禁：默认关闭；无参考图则拒绝（禁止纯文生图）。

示例：
  python tools/shared/design_lineart_gate.py --case-dir outputs/case --check
  python tools/shared/design_lineart_gate.py --enable-design-lineart \\
    --case-dir outputs/case --prepare-jobs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ENABLE_ENV = "PATENT_SKILL_DESIGN_LINEART"

CONFIRM_ZH = (
    "是否开启**外观辅助线稿**？（默认关；仅交底草稿，非申报终稿。"
    "开启后将基于已有实物/参考图生成描述与线稿，**无图则不能开启**。）请回复 **是** 或 **否**。"
)


def parse_enabled(cli_flag: bool) -> bool:
    if cli_flag:
        return True
    return os.environ.get(ENABLE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _load_data(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
        except Exception:
            data = json.loads(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"根须为对象: {path}")
    return data


def _find_schema(case_dir: Path, stem: str) -> Path | None:
    for name in (f"{stem}.yaml", f"{stem}.yml", f"{stem}.json"):
        p = case_dir / name
        if p.is_file():
            return p
    return None


def _resolve_path(case_dir: Path, p: str) -> Path:
    path = Path(p)
    if path.is_file():
        return path.resolve()
    cand = (case_dir / p).resolve()
    if cand.is_file():
        return cand
    return path


def validate_brief(brief: dict[str, Any], case_dir: Path) -> list[str]:
    errors: list[str] = []
    if not brief.get("enabled"):
        errors.append("design_lineart_brief.enabled 不为 true")
    if (brief.get("patent_type") or "design") != "design":
        errors.append("patent_type 须为 design")
    views = brief.get("views") or []
    if not views:
        errors.append("views 为空")
    has_shape = bool(str(brief.get("overall_shape") or "").strip())
    has_points = bool(brief.get("design_points"))
    if not has_shape and not has_points:
        errors.append("overall_shape 与 design_points 不能都空")

    for i, v in enumerate(views):
        if not isinstance(v, dict):
            errors.append(f"views[{i}] 非法")
            continue
        paths = v.get("source_paths") or []
        if not paths:
            errors.append(f"views[{i}] ({v.get('view_name')}) 缺少 source_paths（禁止纯文生图）")
            continue
        ok_any = False
        for raw in paths:
            rp = _resolve_path(case_dir, str(raw))
            if rp.is_file():
                ok_any = True
            else:
                errors.append(f"views[{i}] 源图不存在: {raw}")
        if not ok_any:
            errors.append(f"views[{i}] 无任何可读源图")
    return errors


def collect_source_images_from_plan(plan: dict[str, Any], case_dir: Path) -> list[str]:
    out: list[str] = []
    for fig in plan.get("figures") or []:
        if not isinstance(fig, dict):
            continue
        p = fig.get("path") or ""
        if not p:
            continue
        rp = _resolve_path(case_dir, str(p))
        if rp.is_file():
            out.append(str(rp))
    return out


def build_jobs(brief: dict[str, Any], case_dir: Path) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    assist = case_dir / "lineart_assist"
    assist.mkdir(parents=True, exist_ok=True)
    for i, v in enumerate(brief.get("views") or []):
        if not isinstance(v, dict):
            continue
        resolved = []
        for raw in v.get("source_paths") or []:
            rp = _resolve_path(case_dir, str(raw))
            if rp.is_file():
                resolved.append(str(rp))
        name = str(v.get("view_name") or f"view_{i+1}")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60] or f"view_{i+1}"
        out_path = v.get("output_path") or f"lineart_assist/{safe}_lineart.png"
        prompt = (v.get("gen_prompt") or "").strip()
        if not prompt:
            points = brief.get("design_points") or []
            pts = "；".join(str(x) for x in points[:8])
            prompt = (
                f"Black-and-white patent-style line art of the product in the reference image(s). "
                f"View: {name}. Overall: {brief.get('overall_shape') or ''}. "
                f"Emphasize visible design points: {pts}. "
                f"Goal: {v.get('lineart_goal') or 'clean contours'}. "
                "No color, no photoreal shading, no logos, no invented internal structure; "
                "match proportions and openings in the reference images; white background."
            )
        jobs.append(
            {
                "view_name": name,
                "source_paths": resolved,
                # 兼容字段：与 source_paths 相同；供各宿主把路径当作参考图入参
                "reference_images": resolved,
                "relates_hint": v.get("relates_hint") or [],
                "gen_prompt": prompt,
                "output_path": out_path,
                "absolute_output_path": str((case_dir / out_path).resolve()),
                "forbid_text_only": True,
                "host_hint": (
                    "Use the current host's image generation with these files as visual references; "
                    "do not hardcode a vendor tool name; text-only generation is forbidden."
                ),
            }
        )
    return jobs


def run_check(case_dir: Path, *, enabled: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "enabled_flag": enabled,
        "confirm_prompt_zh": CONFIRM_ZH,
        "errors": [],
        "hints": [],
    }
    if not enabled:
        result["errors"].append(
            f"design_lineart 默认关闭。用户确认「是」后使用 --enable-design-lineart 或 {ENABLE_ENV}=1"
        )
        return result

    brief_path = _find_schema(case_dir, "design_lineart_brief")
    plan_path = _find_schema(case_dir, "figure_plan")
    app_path = _find_schema(case_dir, "appearance_schema")

    if not plan_path and not app_path:
        result["errors"].append("案件目录缺少 figure_plan / appearance_schema")
        return result

    plan = _load_data(plan_path) if plan_path else {}
    sources = collect_source_images_from_plan(plan, case_dir) if plan else []
    if not sources and not brief_path:
        result["errors"].append("figure_plan 中无可用图片路径，禁止开启辅助线稿（禁止纯文生图）")
        result["hints"].append(CONFIRM_ZH)
        return result

    if not brief_path:
        result["errors"].append("缺少 design_lineart_brief.yaml；请先按 design_lineart_assist.md 填写")
        result["hints"].append(f"可用源图数: {len(sources)}")
        return result

    brief = _load_data(brief_path)
    errors = validate_brief(brief, case_dir)
    result["errors"] = errors
    result["brief_path"] = str(brief_path)
    result["ok"] = not errors
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="外观辅助线稿门禁（默认关；无参考图拒绝）")
    p.add_argument("--case-dir", type=Path, help="案件 outputs 目录")
    p.add_argument("--enable-design-lineart", action="store_true")
    p.add_argument("--check", action="store_true", help="仅校验")
    p.add_argument("--prepare-jobs", action="store_true", help="校验通过后写出 jobs JSON")
    p.add_argument("--print-confirm", action="store_true", help="打印反问文案")
    args = p.parse_args(argv)

    if args.print_confirm:
        print(CONFIRM_ZH)
        return 0

    if not args.case_dir:
        p.error("需要 --case-dir（或改用 --print-confirm）")

    enabled = parse_enabled(args.enable_design_lineart)
    case_dir = args.case_dir.resolve()
    if not case_dir.is_dir():
        print(json.dumps({"ok": False, "errors": [f"不是目录: {case_dir}"]}, ensure_ascii=False), file=sys.stderr)
        return 1

    report = run_check(case_dir, enabled=enabled)
    if args.prepare_jobs:
        if not report.get("ok"):
            print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        brief = _load_data(Path(report["brief_path"]))
        jobs = build_jobs(brief, case_dir)
        if not jobs:
            report["ok"] = False
            report["errors"] = list(report.get("errors") or []) + ["未生成任何 job"]
            print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        out = case_dir / "lineart_assist" / "design_lineart_jobs.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ok": True,
            "forbid_text_only": True,
            "jobs": jobs,
            "note": "出图须附带 source_paths/reference_images 作视觉参考；禁止纯文生图；勿写死某一宿主工具名",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report["jobs_path"] = str(out)
        report["job_count"] = len(jobs)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"DESIGN_LINEART_JOBS: {out}", file=sys.stderr)
        return 0

    # default --check
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
