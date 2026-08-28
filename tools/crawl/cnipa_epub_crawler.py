# -*- coding: utf-8 -*-
"""
中国专利公布公告网站点：http://epub.cnipa.gov.cn/ —— **首页「公布公告查询」**（#indexForm / #searchStr）及 **高级查询**（/Advanced，分类号、名称与发明人字段）。

须安装 **Playwright**。浏览器启动见 ``tools/shared/browser.py``（系统 Chrome → Edge → 自带 Chromium；有系统浏览器时不必 ``playwright install chromium``）。若只需内存中解析、不落盘 HTML，优先用同目录 **`cnipa_epub_search.py`**；
本文件侧重 **写出结果页 HTML** 与可插拔的 ``fetch_epub_result_html`` API。

-------------------------------------------------------------------------------
一、整体流程（单次检索）
-------------------------------------------------------------------------------
1. 启动浏览器（默认无头；系统 Chrome → Edge → 自带 Chromium；可用环境变量改为有界面）。
2. 新建浏览器上下文：设定 **桌面 Chrome UA**、**zh-CN**、固定 **视口**（见 ``_new_context``），使请求形态接近普通用户浏览器。
3. ``page.goto`` 站点首页，**wait_until="load"**。
4. **等待首页可检索**：首页在访客到达后会先经 **前端脚本/WAF 一类逻辑**，未通过前 **不会出现** 检索输入框 ``#searchStr``。本实现通过 **周期性轮询 DOM**（每 3 秒一次，总时长见 ``EPUB_WAF_MAX_WAIT_SEC``，默认 180s）直到 ``#searchStr`` 出现；**不是**用 requests 直接 POST 能等价替代的步骤。
5. ``page.fill`` 将关键词写入 ``#searchStr``，对 ``#indexForm`` 执行 **submit**（而非单独点按钮），并等待结果页导航 **commit**。
6. 等待结果页就绪：标题为 **「专利查询结果展示」或「无查询结果」**（见 ``EPUB_TITLE_*`` 常量），且 ``#result`` 内出现列表条目（``div.item`` / ``h1.title``）或明确零结果文案；不等待完整 ``load``。国知局改版时需同步调整常量与 ``_RESULT_PAGE_READY_JS``。
7. ``page.content()`` 取全页 HTML；若处于导航中抛错则 **重试退避**（``_safe_page_content``），避免竞态。
8. 后续解析由 **`cnipa_epub_parse.py`** 完成（本文件 ``search_epub_keyword`` 内会调用）。

-------------------------------------------------------------------------------
二、策略摘要：在解决什么、用了哪些手段
-------------------------------------------------------------------------------
- **为何用 Playwright**：站点依赖 **浏览器内 JavaScript** 渲染与风控后再开放检索框；**纯 HTTP 抓取**往往拿不到含 ``#searchStr`` 的可用首页或拿不到真实结果 DOM。
- **所谓「绕过」**：指 **技术层面** 与无头自动化、静态抓取之间的 gap——通过 **真实 Chromium 内核 + 等待 JS 完成 + 常见浏览器指纹**（UA、语言、viewport）降低「一进来就_submit」的失败率；**不**表示规避法律法规或站点服务条款，用途应限合法检索与交底书查新辅助。
- **反自动化/特征**：启动参数 ``--disable-blink-features=AutomationControlled`` 用于减弱 Chromium 的 **webdriver 自动化开关** 暴露（效果因站点升级而变，非保证）。
- **不覆盖的场景**：图形/滑块验证码、短信验证、强制登录等——若站点突然启用，本脚本**无**专门破解逻辑；可尝试 ``PLAYWRIGHT_HEADED=1`` 人工辅助或改用 **WebSearch**（见 ``prompts/prior_art_search.md``）。

-------------------------------------------------------------------------------
三、检索关键词建议
-------------------------------------------------------------------------------
- 公布站首页检索框对 **多个词** 通常按 **同时包含（AND）** 理解，**词多且专**时极易 **0 条**；**建议每次尽量使用单个词或极短短语** 做一次检索，需要宽召回时可用 **`cnipa_epub_search.py`**（按空白拆成多词、多次检索再合并），或分多次手动换关键词。
- 本脚本命令行默认仍接受一个参数字符串（可含空格）；含空格时与浏览器内一次提交一致，语义上仍是 **整句 AND**，不等同于拆词多查。

-------------------------------------------------------------------------------
环境变量
-------------------------------------------------------------------------------
  EPUB_WAF_MAX_WAIT_SEC  轮询等待 #searchStr 的最长时间，默认 180
  PLAYWRIGHT_HEADED        设为 1 时使用有界面 Chromium
  EPUB_RESULT_HTML         结果页 HTML 完整路径；不设则 tools/_last_result_YYYYMMDDHHmmss.html
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

_TOOLS_DIR = Path(__file__).resolve().parents[1]
_SHARED = _TOOLS_DIR / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from cnipa_epub_parse import (
    EpubSearchHit,
    hits_to_jsonable,
    parse_reported_total,
    parse_search_result_html,
)
from browser import launch_chromium
from stdio_utf8 import ensure_utf8_stdio
from patent_type import (  # noqa: E402
    TYPE_ALL,
    epub_checkbox_states,
    normalize_patent_type,
)


EPUB_BASE = "http://epub.cnipa.gov.cn/"
EPUB_ADVANCED = EPUB_BASE.rstrip("/") + "/Advanced"
# 高级查询页 checkbox（与首页 #fmgb 等不同）
EPUB_ADVANCED_CHECKBOX = {
    "fmgb": "isFmgb",
    "fmsq": "isFmsq",
    "xxsq": "isXx",
    "wgsq": "isWg",
}
# 国知局 /Dxb/IndexQuery 结果页 <title>；改版时须同步单测与 _RESULT_PAGE_READY_JS
EPUB_TITLE_RESULT = "专利查询结果展示"
EPUB_TITLE_NO_HIT = "无查询结果"
# 在浏览器内判断结果页可解析：title + #result DOM（列表或零结果文案）
_RESULT_PAGE_READY_JS = """(titles) => {
    const t = document.title.trim();
    if (t === titles.noHit) return true;
    if (t !== titles.result) return false;
    const r = document.querySelector("#result");
    if (!r) return false;
    if (r.querySelector("div.item, h1.title")) return true;
    const html = r.innerHTML;
    if (
        html.includes("无查询结果") ||
        html.includes("没有找到") ||
        html.includes("未检索到") ||
        html.includes("0条")
    ) {
        return true;
    }
    return false;
}"""
_RESULT_FINGERPRINT_JS = """() => {
    const result = document.querySelector("#result");
    const text = result ? result.innerText.replace(/\s+/g, " ").trim() : "";
    return `${location.href}|${text.slice(0, 2000)}`;
}"""
_RESULT_FINGERPRINT_CHANGED_JS = """(previous) => {
    const result = document.querySelector("#result");
    const text = result ? result.innerText.replace(/\s+/g, " ").trim() : "";
    return `${location.href}|${text.slice(0, 2000)}` !== previous;
}"""
_FETCH_RESULT_PAGE_JS = """async ({pageNum, pageSize, timeoutMs}) => {
    const form = document.querySelector("#query_form");
    if (!form) return {ok: false, error: "missing_query_form"};
    const pageNumInput = form.querySelector("#pageNum");
    const pageSizeInput = form.querySelector("#pageSize");
    if (!pageNumInput || !pageSizeInput) {
        return {ok: false, error: "missing_page_fields"};
    }
    pageNumInput.value = String(pageNum);
    pageSizeInput.value = String(pageSize);
    const searchAfter = form.querySelector("#searchAfter");
    if (searchAfter) searchAfter.value = "";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch(form.action, {
            method: "POST",
            body: new URLSearchParams(new FormData(form)),
            credentials: "same-origin",
            signal: controller.signal,
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        });
        const text = await response.text();
        const doc = new DOMParser().parseFromString(text, "text/html");
        const currentText = doc.querySelector(".current_page")?.textContent || "";
        const totalText = doc.querySelector(".page_total")?.textContent || "";
        const totalMatch = totalText.match(/共\s*(\d+)\s*页/);
        const totalScriptMatch = text.match(/\btotal_page\s*=\s*(\d+)/i) ||
            text.match(/\btotalPage\s*[:=]\s*(\d+)/i);
        const currentScriptMatch = text.match(
            /\bcurrent_page\s*[:=]\s*["']?(\d+)/i
        );
        return {
            ok: response.ok,
            status: response.status,
            text,
            currentPage: Number.parseInt(currentText, 10) ||
                (currentScriptMatch ? Number.parseInt(currentScriptMatch[1], 10) : null),
            totalPages: totalMatch ? Number.parseInt(totalMatch[1], 10) :
                (totalScriptMatch ? Number.parseInt(totalScriptMatch[1], 10) : null),
        };
    } catch (error) {
        return {ok: false, error: String(error)};
    } finally {
        clearTimeout(timer);
    }
}"""
_CLICK_NEXT_PAGE_JS = """() => {
    const candidates = Array.from(document.querySelectorAll(
        'a.next_page, a[rel="next"], button[rel="next"], a, button, ' +
        'input[type="button"], input[type="submit"], span[onclick], li[onclick]'
    ));
    const disabled = (element) => {
        const own = `${element.className || ""} ${element.getAttribute("aria-disabled") || ""}`.toLowerCase();
        const parent = element.parentElement
            ? `${element.parentElement.className || ""} ${element.parentElement.getAttribute("aria-disabled") || ""}`.toLowerCase()
            : "";
        return element.disabled || element.hasAttribute("disabled") ||
            own.includes("disabled") || parent.includes("disabled") ||
            own.includes("btn_dis") || parent.includes("btn_dis") ||
            own.includes("layui-disabled") || parent.includes("layui-disabled");
    };
    for (const element of candidates) {
        if (disabled(element)) continue;
        const text = (element.innerText || element.value || "").replace(/\s+/g, "").trim();
        const rel = (element.getAttribute("rel") || "").toLowerCase();
        const title = (element.getAttribute("title") || "").replace(/\s+/g, "").trim();
        const aria = (element.getAttribute("aria-label") || "").replace(/\s+/g, "").trim();
        const classes = `${element.className || ""} ${element.parentElement?.className || ""}`.toLowerCase();
        const explicit = rel === "next" || title.includes("下一页") || aria.includes("下一页") ||
            text.startsWith("下一页") || text.startsWith("下页");
        const pagerSymbol = [">", "›", "»"].includes(text);
        const classNext = /(^|[\s_-])next([\s_-]|$)/.test(classes);
        if (!explicit && !pagerSymbol && !classNext) continue;
        element.click();
        return {clicked: true, label: text || title || aria || rel || "next"};
    }
    return {clicked: false, label: ""};
}"""
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 个人组合查询会逐一选择官方公布公告目录。
_ADVANCED_TYPE_IDS = EPUB_ADVANCED_CHECKBOX


@dataclass
class EpubPagedSearchResult:
    """All result pages collected for one CNIPA query."""

    hits: list[EpubSearchHit]
    pages_scanned: int
    complete: bool
    stop_reason: str
    total_reported: int | None = None
    html_bytes: int = 0


def _max_wait_sec() -> float:
    return float(os.environ.get("EPUB_WAF_MAX_WAIT_SEC", "180"))


def _headed() -> bool:
    return os.environ.get("PLAYWRIGHT_HEADED", "").strip() in ("1", "true", "yes")


def default_result_html_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return Path(__file__).resolve().parent / f"_last_result_{ts}.html"


def wait_for_epub_home_ready(page: Page, *, max_wait_sec: float | None = None) -> None:
    limit = max_wait_sec if max_wait_sec is not None else _max_wait_sec()
    page.goto(EPUB_BASE, wait_until="load", timeout=120_000)
    elapsed = 0.0
    step = 3.0
    while elapsed < limit:
        page.wait_for_timeout(int(step * 1000))
        elapsed += step
        if page.query_selector("#searchStr"):
            return
    raise TimeoutError(
        f"{limit}s 内未出现检索框 #searchStr；可增大 EPUB_WAF_MAX_WAIT_SEC 或设置 PLAYWRIGHT_HEADED=1"
    )


def open_epub_advanced_search(page: Page) -> None:
    """Open CNIPA's fielded search after the browser session passed the home gate."""
    page.goto(EPUB_ADVANCED, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_selector("#advForm #e72", timeout=120_000)


def _safe_page_content(page: Page, *, max_attempts: int = 10) -> str:
    last_err: Exception | None = None
    for i in range(max_attempts):
        try:
            return page.content()
        except Error as e:
            msg = str(e).lower()
            last_err = e
            if "navigating" not in msg and "changing" not in msg:
                raise
            try:
                page.wait_for_load_state("load", timeout=20_000)
            except Exception:
                pass
            page.wait_for_timeout(400 + 200 * i)
    if last_err:
        raise last_err
    raise RuntimeError("_safe_page_content: 未返回内容")


def _wait_result_page_ready(page: Page) -> None:
    """等结果页 title 与 #result 列表/零结果 DOM 就绪（不等完整 load）。"""
    page.wait_for_function(
        _RESULT_PAGE_READY_JS,
        arg={"result": EPUB_TITLE_RESULT, "noHit": EPUB_TITLE_NO_HIT},
        timeout=120_000,
    )


def _hit_key(hit: EpubSearchHit) -> str:
    return (
        hit.pub_number
        or hit.application_number
        or hit.link
        or (hit.title or "")[:120]
        or hit.raw_html[:120]
    )


def _merge_hits(target: list[EpubSearchHit], incoming: list[EpubSearchHit]) -> None:
    seen = {_hit_key(hit) for hit in target}
    for hit in incoming:
        key = _hit_key(hit)
        if key in seen:
            continue
        seen.add(key)
        target.append(hit)


def advance_to_next_result_page(page: Page) -> str:
    """Advance one result page; return ``advanced``, ``last_page`` or ``stalled``."""
    previous = page.evaluate(_RESULT_FINGERPRINT_JS)
    clicked = page.evaluate(_CLICK_NEXT_PAGE_JS)
    if not clicked or not clicked.get("clicked"):
        return "last_page"
    try:
        page.wait_for_function(
            _RESULT_FINGERPRINT_CHANGED_JS,
            arg=previous,
            timeout=120_000,
        )
        _wait_result_page_ready(page)
    except PlaywrightTimeoutError:
        return "stalled"
    return "advanced"


def apply_epub_type_filter(page: Page, patent_type: str = TYPE_ALL) -> None:
    """按类型勾选首页 #fmgb/#fmsq/#xxsq/#wgsq（与截图四类一致）。"""
    states = epub_checkbox_states(patent_type)
    for cid, want in states.items():
        box = page.query_selector(f"#{cid}")
        if not box:
            continue
        try:
            if want:
                box.check(force=True)
            else:
                box.uncheck(force=True)
        except Error:
            page.evaluate(
                """({id, checked}) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.checked = checked;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('click', { bubbles: true }));
                }""",
                {"id": cid, "checked": want},
            )


def apply_epub_advanced_type_filter(page: Page, patent_type: str = TYPE_ALL) -> None:
    """高级查询页勾选 #isFmgb / #isFmsq / #isXx / #isWg。"""
    states = epub_checkbox_states(patent_type)
    for home_id, want in states.items():
        cid = EPUB_ADVANCED_CHECKBOX.get(home_id)
        if not cid:
            continue
        box = page.query_selector(f"#{cid}")
        if not box:
            continue
        try:
            if want:
                box.check(force=True)
            else:
                box.uncheck(force=True)
        except Error:
            page.evaluate(
                """({id, checked}) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.checked = checked;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('click', { bubbles: true }));
                }""",
                {"id": cid, "checked": want},
            )


def apply_epub_advanced_catalog_filter(page: Page, catalog_id: str) -> None:
    """Select exactly one official publication catalog on the advanced form."""
    if catalog_id not in _ADVANCED_TYPE_IDS:
        raise ValueError(f"unknown CNIPA publication catalog: {catalog_id}")
    for home_id, advanced_id in _ADVANCED_TYPE_IDS.items():
        box = page.query_selector(f"#{advanced_id}")
        if not box:
            raise RuntimeError(f"CNIPA advanced-search checkbox missing: #{advanced_id}")
        want = home_id == catalog_id
        try:
            if want:
                box.check(force=True)
            else:
                box.uncheck(force=True)
        except Error:
            page.evaluate(
                """({id, checked}) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.checked = checked;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                {"id": advanced_id, "checked": want},
            )


def wait_for_epub_advanced_ready(page: Page, *, max_wait_sec: float | None = None) -> None:
    """打开 /Advanced，等到分类号框 #e51。"""
    limit = max_wait_sec if max_wait_sec is not None else _max_wait_sec()
    page.goto(EPUB_ADVANCED, wait_until="load", timeout=120_000)
    elapsed = 0.0
    step = 3.0
    while elapsed < limit:
        page.wait_for_timeout(int(step * 1000))
        elapsed += step
        if page.query_selector("#e51"):
            return
    raise TimeoutError(
        f"{limit}s 内未出现高级查询分类号框 #e51；可增大 EPUB_WAF_MAX_WAIT_SEC"
    )


def submit_advanced_search(
    page: Page,
    keyword: str,
    *,
    class_code: str,
    patent_type: str = TYPE_ALL,
) -> None:
    """高级查询：分类号 #e51 + 名称 #ti，类型勾选后提交。"""
    apply_epub_advanced_type_filter(page, patent_type)
    page.fill("#e51", class_code)
    if page.query_selector("#ti"):
        page.fill("#ti", keyword or "")
    form = page.query_selector("#advForm")
    if form is None:
        raise RuntimeError("高级查询未找到 #advForm")
    btn = form.query_selector("button")
    if btn is None:
        raise RuntimeError("高级查询未找到提交按钮")
    btn.click()
    page.wait_for_url("**/Dxb/AdvancedQuery", timeout=120_000)
    _wait_result_page_ready(page)


def submit_index_search(
    page: Page,
    keyword: str,
    *,
    patent_type: str = TYPE_ALL,
) -> None:
    apply_epub_type_filter(page, patent_type)
    page.fill("#searchStr", keyword)
    with page.expect_navigation(timeout=120_000, wait_until="commit"):
        form = page.query_selector("#indexForm")
        if form:
            form.evaluate("el => el.submit()")
        else:
            page.evaluate(
                """() => {
                const f = document.getElementById('indexForm');
                if (f) f.submit();
            }"""
            )
    _wait_result_page_ready(page)


def submit_advanced_inventor_search(
    page: Page,
    inventor: str,
    *,
    catalog_id: str,
) -> None:
    """Submit the official ``发明（设计）人`` field instead of the home keyword box."""
    if not inventor.strip():
        raise ValueError("inventor must not be empty")
    last_error: Exception | None = None
    for attempt in range(3):
        if attempt:
            open_epub_advanced_search(page)
        apply_epub_advanced_catalog_filter(page, catalog_id)
        page.fill("#e72", inventor.strip())
        try:
            with page.expect_navigation(timeout=120_000, wait_until="commit"):
                page.locator("#advForm button[onclick*='adv_Query']").click()
            _wait_result_page_ready(page)
            return
        except (Error, PlaywrightTimeoutError) as exc:
            last_error = exc
            if page.title().strip() in (EPUB_TITLE_RESULT, EPUB_TITLE_NO_HIT):
                try:
                    _wait_result_page_ready(page)
                    return
                except (Error, PlaywrightTimeoutError):
                    pass
            page.wait_for_timeout(1_000 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("CNIPA advanced inventor search did not start")


def _fetch_result_page_fragment(
    page: Page,
    *,
    page_num: int,
    page_size: int,
    max_attempts: int = 3,
) -> tuple[dict | None, str | None]:
    last_error = None
    for attempt in range(max_attempts):
        result = page.evaluate(
            _FETCH_RESULT_PAGE_JS,
            {"pageNum": page_num, "pageSize": page_size, "timeoutMs": 30_000},
        )
        if result.get("ok") and result.get("text"):
            current_page = result.get("currentPage")
            if current_page is None or int(current_page) == page_num:
                return result, None
            last_error = f"wrong_page:{current_page}"
        else:
            last_error = str(result.get("error") or f"http_{result.get('status')}")
        page.wait_for_timeout(750 * (attempt + 1))
    return None, last_error


def _collect_query_form_result_pages(
    page: Page,
    *,
    max_pages: int,
    page_size: int = 10,
) -> EpubPagedSearchResult:
    """Collect official PageQuery fragments without relying on AJAX DOM callbacks."""
    if page.title().strip() == EPUB_TITLE_NO_HIT:
        return EpubPagedSearchResult(
            hits=[],
            pages_scanned=1,
            complete=True,
            stop_reason="last_page",
        )
    if not page.query_selector("#query_form"):
        return _collect_current_result_pages(page, max_pages=max_pages)

    hits: list[EpubSearchHit] = []
    fingerprints: set[str] = set()
    pages_scanned = 0
    html_bytes = 0
    total_pages = None
    page_num = 1

    while True:
        result, error = _fetch_result_page_fragment(
            page,
            page_num=page_num,
            page_size=page_size,
        )
        if result is None:
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=False,
                stop_reason=f"page_fetch_failed:{page_num}:{error}",
                html_bytes=html_bytes,
            )
        html = str(result["text"])
        html_bytes += len(html)
        digest = hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()
        if digest in fingerprints:
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=False,
                stop_reason=f"repeated_page:{page_num}",
                html_bytes=html_bytes,
            )
        fingerprints.add(digest)
        pages_scanned += 1
        page_hits = parse_search_result_html(html)
        _merge_hits(hits, page_hits)

        if total_pages is None and result.get("totalPages") is not None:
            total_pages = int(result["totalPages"])
        reached_last_page = (
            total_pages is not None and page_num >= total_pages
        ) or (total_pages is None and len(page_hits) < page_size)
        if reached_last_page:
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=True,
                stop_reason="last_page",
                html_bytes=html_bytes,
            )
        if pages_scanned >= max_pages:
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=False,
                stop_reason="max_pages",
                html_bytes=html_bytes,
            )
        page_num += 1


def _collect_current_result_pages(page: Page, *, max_pages: int) -> EpubPagedSearchResult:
    """Collect one already-submitted result set, preserving completeness state."""
    hits: list[EpubSearchHit] = []
    fingerprints: set[str] = set()
    pages_scanned = 0
    total_reported = None
    html_bytes = 0

    while True:
        html = _safe_page_content(page)
        html_bytes += len(html)
        digest = hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()
        if digest in fingerprints:
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=False,
                stop_reason="repeated_page",
                total_reported=total_reported,
                html_bytes=html_bytes,
            )
        fingerprints.add(digest)
        pages_scanned += 1
        if total_reported is None:
            total_reported = parse_reported_total(html)
        _merge_hits(hits, parse_search_result_html(html))

        status = advance_to_next_result_page(page)
        if status == "last_page":
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=True,
                stop_reason=status,
                total_reported=total_reported,
                html_bytes=html_bytes,
            )
        if status == "stalled":
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=False,
                stop_reason=status,
                total_reported=total_reported,
                html_bytes=html_bytes,
            )
        if pages_scanned >= max_pages:
            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=False,
                stop_reason="max_pages",
                total_reported=total_reported,
                html_bytes=html_bytes,
            )


def fetch_epub_result_html(
    keyword: str,
    *,
    patent_type: str = TYPE_ALL,
    playwright_factory: Callable[[], Playwright] | None = None,
) -> str:
    """
    只拉取检索结果页 HTML，不在此函数内做正文解析。
    解析请使用 ``cnipa_epub_parse.parse_search_result_html(html)``。
    """
    rows = search_epub_keywords(
        [keyword], patent_type=patent_type, playwright_factory=playwright_factory
    )
    return rows[0][0]


def search_epub_keywords(
    terms: list[str],
    *,
    patent_type: str = TYPE_ALL,
    class_codes: list[str] | None = None,
    playwright_factory: Callable[[], Playwright] | None = None,
) -> list[tuple[str, list[EpubSearchHit]]]:
    """一场检索共用一个浏览器；一词一页，返回与检索次数等长的 ``(html, hits)``。

    ``class_codes`` 非空时走公布站 **高级查询**（分类号 + 名称）；``terms`` 可为空（只按分类号，保底放宽）。
    """
    codes = [c.strip() for c in (class_codes or []) if c and str(c).strip()]
    if not terms and not codes:
        return []
    kw_list = list(terms) if terms else [""]
    pw_gen = playwright_factory or sync_playwright
    with pw_gen() as p:
        browser = _launch_browser(p)
        context = _new_context(browser)
        try:
            page = context.new_page()
            out: list[tuple[str, list[EpubSearchHit]]] = []
            if not codes:
                for keyword in kw_list:
                    if not keyword:
                        continue
                    wait_for_epub_home_ready(page)
                    submit_index_search(page, keyword, patent_type=patent_type)
                    html = _safe_page_content(page)
                    out.append((html, parse_search_result_html(html)))
                return out
            for code in codes:
                for keyword in kw_list:
                    wait_for_epub_advanced_ready(page)
                    submit_advanced_search(
                        page,
                        keyword,
                        class_code=code,
                        patent_type=patent_type,
                    )
                    html = _safe_page_content(page)
                    out.append((html, parse_search_result_html(html)))
            return out
        finally:
            context.close()
            browser.close()


def search_epub_keyword(
    keyword: str,
    *,
    patent_type: str = TYPE_ALL,
    class_codes: list[str] | None = None,
    playwright_factory: Callable[[], Playwright] | None = None,
) -> tuple[str, list[EpubSearchHit]]:
    rows = search_epub_keywords(
        [keyword],
        patent_type=patent_type,
        class_codes=class_codes,
        playwright_factory=playwright_factory,
    )
    return rows[0]


def search_epub_keyword_all_pages(
    keyword: str,
    *,
    patent_type: str = TYPE_ALL,
    max_pages: int = 100,
    playwright_factory: Callable[[], Playwright] | None = None,
) -> EpubPagedSearchResult:
    """Search one keyword and exhaust CNIPA pagination with explicit completeness."""
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    pw_gen = playwright_factory or sync_playwright
    with pw_gen() as p:
        browser = _launch_browser(p)
        context = _new_context(browser)
        try:
            page = context.new_page()
            wait_for_epub_home_ready(page)
            submit_index_search(page, keyword, patent_type=patent_type)
            return _collect_current_result_pages(page, max_pages=max_pages)
        finally:
            context.close()
            browser.close()


def search_epub_inventor_all_pages(
    inventor: str,
    *,
    patent_type: str = TYPE_ALL,
    max_pages: int = 100,
    playwright_factory: Callable[[], Playwright] | None = None,
) -> EpubPagedSearchResult:
    """Exhaust the official advanced-search inventor field across selected catalogs."""
    if not inventor.strip():
        raise ValueError("inventor must not be empty")
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    selected_catalogs = [
        catalog_id
        for catalog_id, enabled in epub_checkbox_states(patent_type).items()
        if enabled
    ]
    pw_gen = playwright_factory or sync_playwright
    with pw_gen() as p:
        browser = _launch_browser(p)
        context = _new_context(browser)
        try:
            page = context.new_page()
            wait_for_epub_home_ready(page)
            hits: list[EpubSearchHit] = []
            pages_scanned = 0
            html_bytes = 0

            for catalog_id in selected_catalogs:
                remaining_pages = max_pages - pages_scanned
                if remaining_pages < 1:
                    return EpubPagedSearchResult(
                        hits=hits,
                        pages_scanned=pages_scanned,
                        complete=False,
                        stop_reason="max_pages",
                        html_bytes=html_bytes,
                    )
                current = None
                for catalog_attempt in range(3):
                    open_epub_advanced_search(page)
                    submit_advanced_inventor_search(
                        page,
                        inventor,
                        catalog_id=catalog_id,
                    )
                    current = _collect_query_form_result_pages(
                        page,
                        max_pages=remaining_pages,
                    )
                    transient = current.stop_reason.startswith("page_fetch_failed")
                    if current.complete or not transient or catalog_attempt == 2:
                        break
                    page.wait_for_timeout(2_000 * (catalog_attempt + 1))
                if current is None:
                    raise RuntimeError("CNIPA catalog search did not produce a result")
                _merge_hits(hits, current.hits)
                pages_scanned += current.pages_scanned
                html_bytes += current.html_bytes
                if not current.complete:
                    return EpubPagedSearchResult(
                        hits=hits,
                        pages_scanned=pages_scanned,
                        complete=False,
                        stop_reason=f"{catalog_id}:{current.stop_reason}",
                        html_bytes=html_bytes,
                    )

            return EpubPagedSearchResult(
                hits=hits,
                pages_scanned=pages_scanned,
                complete=True,
                stop_reason="all_catalogs_complete",
                html_bytes=html_bytes,
            )
        finally:
            context.close()
            browser.close()


def search_epub_keyword_with_page(
    page: Page,
    keyword: str,
    *,
    patent_type: str = TYPE_ALL,
) -> tuple[str, list[EpubSearchHit]]:
    wait_for_epub_home_ready(page)
    submit_index_search(page, keyword, patent_type=patent_type)
    html = _safe_page_content(page)
    return html, parse_search_result_html(html)


def _launch_browser(p: Playwright) -> Browser:
    browser, _label = launch_chromium(p, headless=not _headed())
    return browser


def _new_context(browser: Browser) -> BrowserContext:
    if sys.platform == "darwin":
        platform_token = "Macintosh; Intel Mac OS X 10_15_7"
    elif sys.platform.startswith("linux"):
        platform_token = "X11; Linux x86_64"
    else:
        platform_token = "Windows NT 10.0; Win64; x64"
    user_agent = DEFAULT_USER_AGENT.format(version=browser.version).replace(
        "Windows NT 10.0; Win64; x64", platform_token
    )
    return browser.new_context(
        user_agent=user_agent,
        locale="zh-CN",
        viewport={"width": 1280, "height": 900},
    )


def _dump_home_debug() -> None:
    """调试：仅拉取首页并保存 WAF 通过后 HTML。"""
    out = Path(__file__).resolve().parent / "_last_home.html"
    with sync_playwright() as p:
        browser = _launch_browser(p)
        context = _new_context(browser)
        page = context.new_page()
        try:
            wait_for_epub_home_ready(page)
            out.write_text(page.content(), encoding="utf-8")
            print("已保存:", out)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    ensure_utf8_stdio()
    argv = [a for a in sys.argv[1:] if a.strip()]
    if argv and argv[0] in ("--dump-home", "-d"):
        _dump_home_debug()
        sys.exit(0)
    patent_type = TYPE_ALL
    filtered: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--type", "-t") and i + 1 < len(argv):
            patent_type = normalize_patent_type(argv[i + 1], default=TYPE_ALL)
            i += 2
            continue
        if a.startswith("--type="):
            patent_type = normalize_patent_type(a.split("=", 1)[1], default=TYPE_ALL)
            i += 1
            continue
        filtered.append(a)
        i += 1
    kw = (filtered[0] if filtered else "批处理").strip()
    try:
        out_html, hits = search_epub_keyword(kw, patent_type=patent_type)
    except Exception as e:
        print("CNIPA_EPUB_ERROR:", e, file=sys.stderr)
        sys.exit(1)
    out_path = Path(
        os.environ.get("EPUB_RESULT_HTML", "").strip() or default_result_html_path()
    )
    out_path = out_path.expanduser().resolve()
    out_path.write_text(out_html, encoding="utf-8")
    print(
        "结果页长度",
        len(out_html),
        "解析条目数",
        len(hits),
        file=sys.stderr,
        flush=True,
    )
    print("结果页 HTML 已保存:", out_path, file=sys.stderr, flush=True)
    print(
        "EPUB_HITS_JSON:",
        json.dumps(hits_to_jsonable(hits), ensure_ascii=False),
        flush=True,
    )
