# -*- coding: utf-8 -*-
"""从国家知识产权局公布公告结果页生成发明人公开专利清单。

脚本使用高级查询页的“发明（设计）人”字段，遍历所选公布公告类型及其全部
结果页，并可按申请人别名过滤同名发明人。输出会明确报告分页是否完成，绝不把
部分结果表述为完整清单。

示例：

  python tools/crawl/cnipa_epub_portfolio.py --inventor "发明人姓名"
  python tools/crawl/cnipa_epub_portfolio.py --inventor "发明人姓名" \
      --applicant "申请主体一" \
      --applicant "申请主体二"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict
from pathlib import Path

_CRAWL = Path(__file__).resolve().parent
_SHARED = _CRAWL.parent / "shared"
for path in (_CRAWL, _SHARED):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from cnipa_epub_parse import EpubSearchHit  # noqa: E402
from patent_type import TYPE_ALL, normalize_patent_type  # noqa: E402


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, TypeError):
            pass


def normalize_identity(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", "", normalized).casefold()


def _matching_applicant(actual: str | None, aliases: list[str]) -> str | None:
    actual_key = normalize_identity(actual)
    if not actual_key:
        return None
    for alias in aliases:
        if normalize_identity(alias) in actual_key:
            return alias
    return None


def filter_portfolio_hits(
    hits: list[EpubSearchHit],
    *,
    inventor: str,
    applicants: list[str] | None = None,
) -> list[dict]:
    """过滤同名记录，并合并同一申请对应的多个公布公告记录。"""
    applicant_aliases = [value.strip() for value in (applicants or []) if value.strip()]
    inventor_key = normalize_identity(inventor)
    rows: list[dict] = []
    row_by_application: dict[str, dict] = {}
    for hit in hits:
        inventor_verified = None
        if hit.inventors:
            inventor_verified = inventor_key in {
                normalize_identity(name) for name in hit.inventors
            }
            if not inventor_verified:
                continue

        matched_applicant = _matching_applicant(hit.applicant, applicant_aliases)
        if applicant_aliases and matched_applicant is None:
            continue

        if inventor_verified:
            identity_status = "verified_inventor_metadata"
        elif applicant_aliases:
            identity_status = "inventor_query_and_applicant"
        else:
            identity_status = "inventor_query_only_unverified_namesake"

        row = asdict(hit)
        row.pop("raw_html", None)
        row["matched_applicant"] = matched_applicant
        row["identity_status"] = identity_status
        publication_record = {
            "pub_number": hit.pub_number,
            "publication_date": hit.publication_date,
            "link": hit.link,
        }
        row["publication_records"] = [publication_record]

        application_key = normalize_identity(hit.application_number)
        if application_key and application_key in row_by_application:
            existing = row_by_application[application_key]
            existing_numbers = {
                record.get("pub_number") for record in existing["publication_records"]
            }
            if publication_record["pub_number"] not in existing_numbers:
                existing["publication_records"].append(publication_record)
            continue
        rows.append(row)
        if application_key:
            row_by_application[application_key] = row
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="检索发明人的全部已公布专利，并按申请人过滤同名结果"
    )
    parser.add_argument("--inventor", required=True, help="发明人/设计人姓名")
    parser.add_argument(
        "--applicant",
        action="append",
        default=[],
        help="申请人名称；可重复传入多个任职单位/申请主体",
    )
    parser.add_argument(
        "--type",
        default=TYPE_ALL,
        help="invention|utility_model|design|all（默认 all）",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="最多遍历结果页数；达到上限将标记为不完整并返回非零状态",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    args = _build_parser().parse_args(argv)
    try:
        patent_type = normalize_patent_type(args.type, default=TYPE_ALL)
    except ValueError as exc:
        print(f"ERROR: 专利类型参数无效：{exc}", file=sys.stderr)
        return 2
    if args.max_pages < 1:
        print("ERROR: --max-pages 必须至少为 1", file=sys.stderr)
        return 2

    try:
        import playwright  # noqa: F401
    except ImportError:
        print(
            "ERROR: 请安装 tools/crawl/requirements-cnipa.txt 中的依赖和 Playwright Chromium",
            file=sys.stderr,
        )
        return 1

    from cnipa_epub_crawler import search_epub_inventor_all_pages

    try:
        search = search_epub_inventor_all_pages(
            args.inventor.strip(),
            patent_type=patent_type,
            max_pages=args.max_pages,
        )
    except Exception as exc:
        print(f"CNIPA_EPUB_ERROR: {exc}", file=sys.stderr)
        return 1

    matched = filter_portfolio_hits(
        search.hits,
        inventor=args.inventor,
        applicants=args.applicant,
    )
    payload = {
        "source": "http://epub.cnipa.gov.cn/Advanced",
        "scope": "published_records_only",
        "query_mode": "advanced_inventor_field",
        "query": {
            "inventor": args.inventor.strip(),
            "applicants": args.applicant,
            "patent_type": patent_type,
        },
        "complete": search.complete,
        "stop_reason": search.stop_reason,
        "pages_scanned": search.pages_scanned,
        "total_reported": search.total_reported,
        "candidate_count": len(search.hits),
        "matched_count": len(matched),
        "matched_publication_count": sum(
            len(row["publication_records"]) for row in matched
        ),
        "hits": matched,
    }
    print(
        "EPUB_PORTFOLIO_JSON:",
        json.dumps(payload, ensure_ascii=False),
        flush=True,
    )
    print(
        "EPUB_PORTFOLIO_NOTE: pages=%d candidates=%d matched=%d complete=%s stop=%s"
        % (
            search.pages_scanned,
            len(search.hits),
            len(matched),
            str(search.complete).lower(),
            search.stop_reason,
        ),
        file=sys.stderr,
        flush=True,
    )
    if not search.complete:
        print(
            "EPUB_PORTFOLIO_INCOMPLETE: 分页未完整遍历，不得将本次结果表述为完整专利清单",
            file=sys.stderr,
            flush=True,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
