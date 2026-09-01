# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "crawl"))
sys.path.insert(0, str(ROOT / "tools" / "shared"))

from cnipa_epub_crawler import (  # noqa: E402
    DEFAULT_USER_AGENT,
    _CLICK_NEXT_PAGE_JS,
    _FETCH_RESULT_PAGE_JS,
    _collect_query_form_result_pages,
    advance_to_next_result_page,
    apply_epub_advanced_catalog_filter,
    submit_advanced_inventor_search,
)
from cnipa_epub_parse import (  # noqa: E402
    EpubSearchHit,
    normalize_application_number,
    parse_reported_total,
    parse_search_result_html,
)
from cnipa_epub_portfolio import filter_portfolio_hits  # noqa: E402


class ListResultParserTests(unittest.TestCase):
    def test_parses_application_applicant_and_title(self) -> None:
        html = """
        <table><tbody><tr>
          <td>2</td>
          <td><a href="/patent/CN120000001A">2026101234567</a></td>
          <td>示例<em>人工智能</em>研究院</td>
          <td>一种示例数据处理方法、装置及电子设备</td>
        </tr></tbody></table>
        """
        hits = parse_search_result_html(html)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].application_number, "202610123456.7")
        self.assertEqual(hits[0].applicant, "示例 人工智能 研究院")
        self.assertEqual(
            hits[0].title, "一种示例数据处理方法、装置及电子设备"
        )
        self.assertEqual(
            hits[0].link, "http://epub.cnipa.gov.cn/patent/CN120000001A"
        )

    def test_normalizes_application_number_with_or_without_dot(self) -> None:
        self.assertEqual(
            normalize_application_number("2025123456789"), "202512345678.9"
        )
        self.assertEqual(
            normalize_application_number("CN202512345678.9"), "202512345678.9"
        )


class CardResultParserTests(unittest.TestCase):
    def test_parses_bibliographic_metadata(self) -> None:
        html = """
        <div class="overview-default">
          <div class="item">
            <h1 class="title">一种示例数据处理方法</h1>
            <dl>
              <dt>申请公布号：</dt><dd>CN120000001A</dd>
              <dt>申请号：</dt><dd>2026101234567</dd>
              <dt>申请人：</dt><dd>示例人工智能研究院</dd>
              <dt>申请日：</dt><dd>2026.04.22</dd>
              <dt>申请公布日：</dt><dd>2026.08.18</dd>
              <dt>发明人：</dt><dd>测试发明人;共同发明人甲;共同发明人乙</dd>
              <dt>摘要：</dt><dd>本发明提供一种示例数据处理方法。</dd>
            </dl>
            <div class="qrcode" title="http://epub.cnipa.gov.cn/patent/CN120000001A"></div>
          </div>
        </div>
        """
        hits = parse_search_result_html(html)
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit.application_number, "202610123456.7")
        self.assertEqual(hit.applicant, "示例人工智能研究院")
        self.assertEqual(
            hit.inventors, ["测试发明人", "共同发明人甲", "共同发明人乙"]
        )
        self.assertEqual(hit.filing_date, "2026.04.22")
        self.assertEqual(hit.publication_date, "2026.08.18")
        self.assertEqual(hit.pub_number, "CN120000001A")

    def test_parses_reported_total(self) -> None:
        self.assertEqual(parse_reported_total("<div>共 68 条</div>"), 68)


class PaginationTests(unittest.TestCase):
    def test_official_next_page_selector_is_supported(self) -> None:
        self.assertIn("a.next_page", _CLICK_NEXT_PAGE_JS)
        self.assertIn('text.startsWith("下页")', _CLICK_NEXT_PAGE_JS)

    def test_page_query_fetch_has_timeout_and_disables_search_after(self) -> None:
        self.assertIn("AbortController", _FETCH_RESULT_PAGE_JS)
        self.assertIn('searchAfter.value = ""', _FETCH_RESULT_PAGE_JS)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', _FETCH_RESULT_PAGE_JS)

    def test_advances_and_waits_for_changed_result(self) -> None:
        page = MagicMock()
        page.evaluate.side_effect = ["old-fingerprint", {"clicked": True}]
        self.assertEqual(advance_to_next_result_page(page), "advanced")
        self.assertEqual(page.wait_for_function.call_count, 2)

    def test_detects_last_page(self) -> None:
        page = MagicMock()
        page.evaluate.side_effect = ["old-fingerprint", {"clicked": False}]
        self.assertEqual(advance_to_next_result_page(page), "last_page")
        page.wait_for_function.assert_not_called()

    def test_reports_stalled_page_instead_of_silent_completion(self) -> None:
        page = MagicMock()
        page.evaluate.side_effect = ["old-fingerprint", {"clicked": True}]
        page.wait_for_function.side_effect = PlaywrightTimeoutError("unchanged")
        self.assertEqual(advance_to_next_result_page(page), "stalled")

    def test_missing_total_uses_short_last_page(self) -> None:
        page = MagicMock()
        page.title.return_value = "专利查询结果展示"
        page.query_selector.return_value = MagicMock()

        def cards(start: int, count: int) -> str:
            items = "".join(
                f'<div class="item"><h1 class="title">专利 {index}</h1></div>'
                for index in range(start, start + count)
            )
            return f'<div class="overview-default">{items}</div>'

        responses = [
            ({"text": cards(1, 10), "totalPages": None}, None),
            ({"text": cards(11, 2), "totalPages": None}, None),
        ]
        with patch(
            "cnipa_epub_crawler._fetch_result_page_fragment",
            side_effect=responses,
        ):
            result = _collect_query_form_result_pages(page, max_pages=100)

        self.assertTrue(result.complete)
        self.assertEqual(result.pages_scanned, 2)
        self.assertEqual(len(result.hits), 12)


class AdvancedInventorSearchTests(unittest.TestCase):
    def test_user_agent_does_not_leak_a_version_placeholder(self):
        self.assertNotIn("{version}", DEFAULT_USER_AGENT)

    def test_selects_one_official_catalog(self) -> None:
        page = MagicMock()
        boxes = {
            cid: MagicMock() for cid in ("isFmgb", "isFmsq", "isXx", "isWg")
        }
        page.query_selector.side_effect = lambda selector: boxes.get(selector[1:])

        apply_epub_advanced_catalog_filter(page, "fmsq")

        boxes["isFmsq"].check.assert_called_once_with(force=True)
        boxes["isFmgb"].uncheck.assert_called_once_with(force=True)
        boxes["isXx"].uncheck.assert_called_once_with(force=True)
        boxes["isWg"].uncheck.assert_called_once_with(force=True)

    def test_submits_the_e72_inventor_field(self) -> None:
        page = MagicMock()
        boxes = {
            cid: MagicMock() for cid in ("isFmgb", "isFmsq", "isXx", "isWg")
        }
        form = MagicMock()

        def query_selector(selector: str):
            if selector == "#advForm":
                return form
            if selector == "#sizeSelect":
                return None
            return boxes.get(selector[1:])

        page.query_selector.side_effect = query_selector

        submit_advanced_inventor_search(page, " 测试发明人 ", catalog_id="fmgb")

        page.fill.assert_called_once_with("#e72", "测试发明人")
        page.expect_navigation.assert_called_once_with(
            timeout=120_000, wait_until="commit"
        )
        page.locator.assert_called_once_with(
            "#advForm button[onclick*='adv_Query']"
        )
        page.locator.return_value.click.assert_called_once_with()


class PortfolioFilterTests(unittest.TestCase):
    def test_filters_same_name_results_by_applicant(self) -> None:
        hits = [
            EpubSearchHit(
                raw_html="",
                application_number="202610123456.7",
                applicant="示例人工智能研究院",
                inventors=["测试发明人", "共同发明人甲"],
                title="一种示例数据处理方法",
            ),
            EpubSearchHit(
                raw_html="",
                application_number="202610765432.1",
                applicant="另一示例研究院",
                inventors=["测试发明人"],
                title="一种示例检测方法",
            ),
        ]
        rows = filter_portfolio_hits(
            hits,
            inventor="测试发明人",
            applicants=["示例人工智能研究院"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["application_number"], "202610123456.7")
        self.assertEqual(rows[0]["identity_status"], "verified_inventor_metadata")

    def test_marks_list_mode_match_basis_explicitly(self) -> None:
        hit = EpubSearchHit(
            raw_html="",
            application_number="202010123456.7",
            applicant="示例网络技术有限公司",
            title="一种示例目标检测方法",
        )
        rows = filter_portfolio_hits(
            [hit],
            inventor="测试发明人",
            applicants=["示例网络技术有限公司"],
        )
        self.assertEqual(rows[0]["identity_status"], "inventor_query_and_applicant")

    def test_merges_publication_and_grant_for_one_application(self) -> None:
        hits = [
            EpubSearchHit(
                raw_html="",
                application_number="202010123456.7",
                pub_number="CN112000001A",
                applicant="示例网络技术有限公司",
                inventors=["测试发明人"],
            ),
            EpubSearchHit(
                raw_html="",
                application_number="202010123456.7",
                pub_number="CN112000001B",
                applicant="示例网络技术有限公司",
                inventors=["测试发明人"],
            ),
        ]
        rows = filter_portfolio_hits(
            hits,
            inventor="测试发明人",
            applicants=["示例网络技术有限公司"],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            [record["pub_number"] for record in rows[0]["publication_records"]],
            ["CN112000001A", "CN112000001B"],
        )


if __name__ == "__main__":
    unittest.main()
