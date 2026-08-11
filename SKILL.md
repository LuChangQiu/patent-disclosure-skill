---
name: patent-disclosure-skill
description: "中国专利：从项目文档挖掘专利点并生成可交付技术交底书（支持发明/实用新型/外观；可选 STEP 多视角解析，默认关闭；可选外观/实用结构辅助线稿，默认关闭；查新、脱敏成文、自检与迭代）；或将已有专利解读为通俗笔记与 Obsidian 知识图谱。| China patents: draft disclosures (invention / utility model / design; optional STEP views; optional design/structure lineart assists) or read patents into plain notes and an Obsidian graph."
version: "3.1.0"
user-invocable: true
argument-hint: "[可选：项目路径 / 技术主题 / 专利号或 PDF 路径]"
allowed-tools: Read, Write, Edit, Grep, Glob, WebSearch, Bash
---

# 中国专利 · 交底书编写与通俗解读

本技能**单包模块化**：分步指令在 **`prompts/`**，执行前须 **`Read`** 对应文件。`SKILL.md` 只做路由。

| 模式 | 何时用 | 主入口 |
|------|--------|--------|
| **A · 交底书编写** | 挖专利点 → 查新 → 成稿 → 迭代 | `prompts/disclosure/`（类型子目录见下） |
| **B · 专利通俗解读** | 公开号 / PDF / 全文 → 通俗笔记 + 图谱 | `prompts/reader/patent_plain_reader.md` |

提供**专利号或专利全文/PDF**且意图为「读懂」时 → **优先模式 B**，**不**默认跑交底书 Step 1–8。

## 目录约定（薄路由）

```
prompts/disclosure/          # 交底公共流程
  invention/                 # 发明：挖点 / builder / template
  utility_model/             # 实用新型：挖点 / builder / template（单独 md，勿套用发明 mermaid 主线）
  design/                    # 外观设计：挖点 / builder / template（单独 md）
prompts/reader/              # 通俗解读 + type_hooks
prompts/shared/              # 写读共用：Structure / Appearance 填表 + figure_plan + 外观/实用辅助线稿
references/schemas/          # structure / appearance / figure_plan / design_lineart_brief / structure_lineart_brief
tools/crawl/                 # 国知局等爬取
tools/shared/                # docx/mermaid/专利类型/可选 STEP / 可选辅助线稿门禁
tools/patent_reader/         # 解读工具：shared/ | extract/ | analyze/ | vault/
```

## 环境与约定

- **语言**：默认与用户语种一致；专利与法律术语用行业常用表述。
- **专利类型**：未显式指定时交底**默认发明**；材料更偏实用/外观时在汇总或预览阶段**反问**（见 `disclosure/intake.md`）。
- **交底书图示**：
  - **发明**：3.2 / 3.4 用 fenced **mermaid** → `tools/shared/mermaid_render.py`；见 `tools/README.md`。
  - **实用新型**：先 `figure_plan.yaml` 排序入文图（优先线稿/CAD；总装+局部写 `relates_to`）+ 部件/关系表（见 `utility_model/disclosure_builder.md`）。
  - **外观**：先 `figure_plan.yaml` 选视图（实拍/线稿均可；多视写 `relates_to`；场景图默认低优先）（见 `design/disclosure_builder.md`）。
- **STEP / CAD（可选，默认关）**：Step 2 用 `cad_scan.py` 分类；遇 `.step`/`.stp` **先反问**再装 `requirements-step.txt` 并 `step_to_views.py --enable-step-parse`；仅有原生 CAD 则回复末尾提示导出 STEP。见 `project_scan.md`「CAD / STEP」。
- **外观辅助线稿（可选，默认关）**：有产品图时可反问；用户 **是** 后按 `shared/design_lineart_assist.md`（先 YAML 描述 + 多视联读，再**参考图**出线稿）；无图禁止；非申报终稿；**不**画部件序号。
- **实用结构辅助线稿（可选，默认关）**：有结构图且缺干净线稿时可反问；用户 **是** 后按 `shared/structure_lineart_assist.md`（对齐 `structure_schema.parts`；轮廓与序号分层，推荐 overlay；禁止自创件号）；无图禁止；非申报终稿。**勿**与外观 `design_lineart_*` 混用。
- **解读 + Obsidian**：强烈推荐配置库；见 **`docs/obsidian-setup-guide.md`**。

---

## 触发条件

- **交底书**：专利挖掘、交底书、查新、实用新型、外观设计等；`/patent-disclosure-skill`、`/交底书`。
- **通俗解读**：读专利、公开号 / PDF 且目标为理解；`/patent-read`、`/读专利`。
- **交底书迭代**：已有交底上补材料/纠错 → `disclosure/iteration_context.md` → `merger` / `correction_handler`；另存时间戳稿。

---

## 工具与数据来源

| 任务 | 建议方式 |
|------|----------|
| 加载分步指令 | **`Read`** → `prompts/disclosure|reader|shared/…`（完整子路径） |
| Word / PPT → Markdown | `tools/shared/docx_to_md.py` / `pptx_to_md.py` |
| CAD 扫描 / STEP→多视图（可选，默认关） | `tools/shared/cad_scan.py`；用户确认后 `step_to_views.py --enable-step-parse` |
| 外观辅助线稿（可选，默认关） | `prompts/shared/design_lineart_assist.md`；门禁 `design_lineart_gate.py`（须参考图，禁止纯文生图） |
| 实用结构辅助线稿（可选，默认关） | `prompts/shared/structure_lineart_assist.md`；门禁 `structure_lineart_gate.py`（须参考图 + Structure；序号优先 overlay） |
| 联网查新 | **`Read`** `disclosure/prior_art_search.md`。优先 **`tools/crawl/cnipa_epub_search.py --type …`**（与 intake 类型一致）；`abstract` 必用；异常再 WebSearch。类型映射见 `references/patent_type_search.yaml` |
| 交底定稿 | 发明：`tools/shared/mermaid_render.py` → md+docx；实用/外观：按各类型 builder |
| 专利通俗解读 | **`Read`** `reader/patent_plain_reader.md`；实用/外观另 Read `reader/type_hooks.md` + `shared/fill_*` |
| 解读取 PDF / 入库 | `tools/patent_reader/extract/fetch_patent_pdf.py`；`…/vault/write_patent_obsidian_note.py` 等（见 `tools/patent_reader/README.md`） |

---

## Prompt 文件映射

### 交底书（公共 + 类型特化）

| 步骤 | 文件 | 用途 |
|------|------|------|
| Step 1 | `prompts/disclosure/intake.md` | 边界；**默认发明**；可反问实用/外观 |
| Step 2 | `prompts/disclosure/project_scan.md` | 项目扫描（Office + **可选 CAD/STEP**；三类示例加扫） |
| Step 3–4 | **发明** `disclosure/invention/patent_points_analyzer.md`；**实用** `utility_model/patent_points.md`；**外观** `design/patent_points.md` | 挖点（**分文件，勿混用**） |
| 填表（实用/外观） | `prompts/shared/fill_structure_schema.md` / `fill_appearance_schema.md` | 图→schema + **`figure_plan.yaml`** |
| 外观辅助线稿 | `prompts/shared/design_lineart_assist.md` | 可选；默认关；描述→参考图线稿（无件号） |
| 实用结构辅助线稿 | `prompts/shared/structure_lineart_assist.md` | 可选；默认关；轮廓→按 parts 叠序号 |
| Step 5 | `prompts/disclosure/prior_art_search.md` | 查新（`--type`） |
| Step 6 | `prompts/disclosure/disclosure_preview.md` | 摘要预览（按类型裁剪） |
| Step 7 | 对应类型目录 `disclosure_builder.md` + `template_reference.md` | 成文（**分文件**） |
| Step 8 | `prompts/disclosure/disclosure_self_check.md` | 内部自检（含 §8.4 / §8.5） |
| 迭代 | `disclosure/iteration_context.md` / `merger.md` / `correction_handler.md` | 另存 |

### 专利通俗解读

| 步骤 | 文件 |
|------|------|
| 主流程 | `prompts/reader/patent_plain_reader.md` |
| 类型挂钩 | `prompts/reader/type_hooks.md` |
| 写笔记 | `reader/obsidian_ofm_companion.md` + `references/patent_obsidian_format.md` |
| 自检 / 插件引导 | `reader/patent_reader_self_check.md` / `obsidian_plugin_guide.md` |
| 取 PDF | `tools/patent_reader/extract/fetch_patent_pdf.py` |
| 入库 | `tools/patent_reader/vault/write_patent_obsidian_note.py` |

---

## 模式 A · 交底书主流程

1. **`Read`** `disclosure/intake.md` → Step 1（默认发明）  
2. **`Read`** `disclosure/project_scan.md` → Step 2  
3. 按类型 **`Read`** `invention|utility_model|design` 挖点；实用/外观先/并行 **`Read`** `shared/fill_*`  
4. **`Read`** `disclosure/prior_art_search.md` → Step 5（`--type` 对齐）  
5. **`Read`** `disclosure/disclosure_preview.md` → Step 6（可跳过；此处可类型反问）  
6. **`Read`** **同类型** `disclosure_builder` + `template_reference` → Step 7（**禁止**用发明 builder 写实用/外观）  
7. **`Read`** `disclosure/disclosure_self_check.md` → Step 8  

**禁止**：交底书正文出现「自检清单」章节。

---

## 模式 B · 专利通俗解读

1. **`Read`** `reader/patent_plain_reader.md`（门禁 / fetch / extract / 线索 / 入库）  
2. 若实用新型或外观：**`Read`** `reader/type_hooks.md` + 对应 `shared/fill_*`  
3. **`Read`** ofm + 自检；入库后可选插件引导；≥2 篇反问关联  

**与模式 A 互斥**：解读不跑交底 Step 1–8。

---

## 迭代模式（交底书 · 摘要）

- 补材料 / 扩展：`iteration_context` → `merger` → 新时间戳稿（实用/外观若改图或主题须同步 **`figure_plan`**）  
- 纠错：`iteration_context` → `correction_handler` → 新时间戳稿（同上）  

---

## Agent 自用工作流检查清单

```
□ 已区分模式 A / B / 迭代，未混跑
□ 交底未指定类型时已默认发明；材料偏实用/外观已按需反问
□ Step 3–4 / Step 7 已 Read 对应类型子目录 md（非发明套用实用/外观）
□ 查新 cnipa 已带与案件一致的 --type；abstract 必用
□ 实用/外观已走 schema 填表（shared）并写出 figure_plan（含必要 relates_to），未看图直接长文；成文只嵌清单入文图
□ Step 2/补材料已 cad_scan：遇 STEP 先反问再装依赖；仅原生 CAD 则回复末尾提示导出 STEP；未确认不开 step_to_views
□ 外观若开启辅助线稿：有用户「是」、有参考图、经 design_lineart_gate；未纯文生图；辅助条默认不入正文
□ 实用若开启结构辅助线稿：有用户「是」、有参考图+Structure、经 structure_lineart_gate；件号对齐 parts；优先 overlay；未自创件号；辅助条默认不入正文
□ 迭代改材料/主题时已重评 figure_plan（含图际关联）
□ 解读实用/外观：公开号种类码或 patent_type.py / fetch 状态已判别类型，并 Read type_hooks + 共用 schema（用户未口头声明也可）
□ 路径使用 prompts/disclosure|reader|shared 与 tools/crawl|shared|patent_reader/{extract,analyze,vault,shared}
```
