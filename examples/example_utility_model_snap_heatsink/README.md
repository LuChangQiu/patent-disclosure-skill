# 示例案件：弹臂卡扣式散热片安装结构（实用新型）

**教学案件**，专利类型：**实用新型**。仅含 `knowledge/` 原材料，用于交底书 Step 2 扫描 + StructureSchema 识图演练，以及**可选 STEP 解析**冒烟。

> 附图已替换为公开专利**真实附图**（散热器卡扣固定件，US6301113B1）。结构说明仍为教学虚构 brief，与附图主题相近但**非**同一中国案件。  
> `knowledge/cad/demo_snap_plate.step` 为技能自生成的**教学几何**（基板 + 卡钩示意），仅用于验证 `cad_scan` / `step_to_views`，**不是**真实产品 CAD。

## 目录

| 路径 | 说明 |
|------|------|
| `knowledge/docs/structure_brief.md` | 结构说明（扫描主文档） |
| `knowledge/assets/fig1_assembly_side.png` | 卡扣固定件装配图（真实专利附图） |
| `knowledge/assets/fig2_snap_detail.png` | 卡扣细节图（真实专利附图） |
| `knowledge/cad/demo_snap_plate.step` | 教学用 STEP（触发「反问是否开启 STEP 解析」） |

> 不提供预填 StructureSchema / figure_plan：须按 `fill_structure_schema.md` 识图自填，产出写入工作目录（勿写回 `knowledge/`）。成文只嵌 `figure_plan` 中入文图（优先线稿/结构图）。

## Agent 话术（可复制）

```text
请按 patent-disclosure-skill 交底书流程执行：
- 专利类型：实用新型
- 项目扫描目录：examples/example_utility_model_snap_heatsink/knowledge/
- Step 2 会 cad_scan 发现 demo_snap_plate.step：请先反问是否开启 STEP 解析（默认关；我回 **是** / **否**）；若否，则只用 assets 位图
- 先 Read prompts/shared/fill_structure_schema.md，对照 assets 图填 StructureSchema，并写出 outputs 下 figure_plan.yaml（优先线稿入文；图2→图1 写 relates_to: detail_of）
- 可选：反问是否开启实用新型结构辅助线稿（默认否；我回 **是** / **否**）。若是，按 structure_lineart_assist.md（须参考图 + Structure；件号对齐 parts；推荐 overlay）
- 再按 prompts/disclosure/utility_model/ 挖点与成文（只嵌 figure_plan 入文图）
- 查新：cnipa_epub_search.py --type utility_model …
```

产出落到 `outputs/{案件标识}/`。细则见 `prompts/disclosure/utility_model/disclosure_builder.md`。

## 可选：验证 STEP 扫描 / 多视角（默认关闭）

轻量扫描（**无需** CadQuery）：

```bash
python tools/shared/cad_scan.py -r examples/example_utility_model_snap_heatsink/knowledge --json
# 期望 action == ask_enable_step_parse，且 step_files 含 demo_snap_plate.step
```

重新生成教学 STEP（若文件丢失）：

```bash
python tools/shared/gen_demo_snap_step.py
```

用户回复 **是** 确认开启后（需 CadQuery，建议 Python 3.9–3.12）：

```bash
pip install -r tools/shared/requirements-step.txt
python tools/shared/step_to_views.py --enable-step-parse \
  -i examples/example_utility_model_snap_heatsink/knowledge/cad/demo_snap_plate.step \
  -o outputs/demo_snap_heatsink_cad_views
```

## 附图来源与下载链接

国内转载站（X技术 / Soopat）对脚本常返回空壳或登录页，**附图不可直链**；下列为已入库文件的可复现下载地址。

| 本地文件 | 来源 | 直链 |
|----------|------|------|
| `fig1_assembly_side.png` | [US6301113B1](https://patents.google.com/patent/US6301113B1/en) sheet D00000 | https://patentimages.storage.googleapis.com/9d/e5/90/4e56a89105a3f3/US06301113-20011009-D00000.png |
| `fig2_snap_detail.png` | 同上 sheet D00001 | https://patentimages.storage.googleapis.com/bb/d6/a8/28ac534381d146/US06301113-20011009-D00001.png |

备份同图：`US6301113B1_fig1.png` / `US6301113B1_fig2.png`。

### 国内说明书文字对照（无附图直链）

| 主题 | 公开号/申请 | 页面 |
|------|-------------|------|
| 散热器鳍片组卡扣结构 | CN209861402U | https://www.xjishu.com/zhuanli/38/201920205694.html |
| 扣合型散热装置 | — | https://www.xjishu.com/zhuanli/59/200720172669.html |

### 可选：国知局命中 PDF 演练

```bash
python tools/patent_reader/extract/fetch_patent_pdf.py --pub CN209861402U -o examples/example_utility_model_snap_heatsink/knowledge
```
