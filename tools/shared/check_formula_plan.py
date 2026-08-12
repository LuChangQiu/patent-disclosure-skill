#!/usr/bin/env python
"""校验案件 formula_plan：范式 id、禁装饰音、数值例等。

用法：
  python tools/shared/check_formula_plan.py -i outputs/某案/formula_plan.yaml
  python tools/shared/check_formula_plan.py -i plan.yaml --case-dir outputs/某案
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.shared.formula_paradigms import (  # noqa: E402
    combo_by_id,
    load_paradigms,
    paradigm_by_id,
)


def _load(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise SystemExit("需要 PyYAML") from exc
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise SystemExit("formula_plan 根须为 mapping")
    return data


def check_plan(plan: dict[str, Any], case_dir: str | Path | None = None) -> dict[str, Any]:
    cfg = load_paradigms(case_dir)
    rules = cfg.get("rules") or {}
    errors: list[str] = []
    warnings: list[str] = []

    pids = [str(x).strip() for x in (plan.get("paradigm_ids") or []) if str(x).strip()]
    combo_id = str(plan.get("combo_id") or "").strip()
    if combo_id:
        combo = combo_by_id(cfg, combo_id)
        if not combo:
            errors.append(f"未知 combo_id: {combo_id}")
        else:
            for pid in combo.get("paradigm_ids") or []:
                if str(pid) not in pids:
                    warnings.append(f"combo {combo_id} 含 {pid}，但 paradigm_ids 未列出（建议补全）")

    if not pids and (plan.get("equations") or plan.get("plain_zh")):
        errors.append("有公式提纲但 paradigm_ids 为空")

    for pid in pids:
        if not paradigm_by_id(cfg, pid):
            errors.append(f"未知 paradigm_id: {pid}")

    eqs = plan.get("equations") or []
    if not isinstance(eqs, list):
        errors.append("equations 须为列表")
        eqs = []

    forbid = list(rules.get("forbid_accent_commands") or [])
    if rules.get("forbid_accents", True) and not forbid:
        forbid = [r"\tilde", r"\hat", r"\bar", r"\breve", r"\vec"]

    latex_blobs: list[str] = []
    for i, eq in enumerate(eqs):
        if not isinstance(eq, dict):
            errors.append(f"equations[{i}] 须为 mapping")
            continue
        epid = str(eq.get("paradigm_id") or "").strip()
        if epid and not paradigm_by_id(cfg, epid):
            errors.append(f"equations[{i}].paradigm_id 未知: {epid}")
        if epid and epid not in pids:
            warnings.append(f"equations[{i}] 使用 {epid} 但未列入 paradigm_ids")
        lx = str(eq.get("latex") or "")
        latex_blobs.append(lx)
        normalized = lx.replace("\\\\", "\\")
        for cmd in forbid:
            token = cmd if str(cmd).startswith("\\") else f"\\{cmd}"
            if token in normalized:
                errors.append(f"equations[{i}] 含禁用装饰音 {token}")

    plain = str(plan.get("plain_zh") or "").strip()
    if eqs and not plain:
        warnings.append("建议填写 plain_zh（主关系人话）")

    if rules.get("require_numeric_example", True) and (eqs or pids):
        ne = plan.get("numeric_example") or {}
        if not isinstance(ne, dict) or not (ne.get("given") or ne.get("result")):
            errors.append("缺少 numeric_example.given / result（可算数值例）")

    syms = plan.get("symbols") or []
    max_sym = int(rules.get("max_free_symbols") or 0)
    if max_sym and isinstance(syms, list) and len(syms) > max_sym:
        warnings.append(f"symbols 共 {len(syms)} 个，超过建议上限 {max_sym}")

    # 裸 max(1, …) 启发式
    blob = "\n".join(latex_blobs)
    if re.search(r"max\s*\(\s*1\s*,", blob, re.I):
        warnings.append("检测到 max(1, …)：请确认 1 与分母同量纲，否则改用 ε")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "paradigm_count": len(cfg.get("paradigms") or []),
        "sources": cfg.get("_sources"),
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--input", required=True, help="formula_plan.yaml|json")
    ap.add_argument("--case-dir", default="", help="案件目录（加载覆盖范式）")
    args = ap.parse_args(argv)

    path = Path(args.input)
    if not path.is_file():
        raise SystemExit(f"找不到: {path}")
    case = args.case_dir.strip() or str(path.parent)
    plan = _load(path)
    result = check_plan(plan, case_dir=case)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
