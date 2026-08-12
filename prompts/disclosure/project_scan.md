# 项目文档扫描（Step 2）

## 目标

按优先级扫描并提取**可专利化**内容。**根据当前项目结构调整扫描路径**。

## 优先级表

| 优先级 | 文档类型 | 关注内容 |
|--------|----------|----------|
| 1 | 专利相关文档 | 专利点分析、已有交底书、专利申报建议、创新点汇总 |
| 2 | 详细设计/方案文档 | 详细设计、方案讨论、流程图、完整流程、技术对比分析 |
| 3 | 核心实现代码 | 算法与策略实现、业务逻辑与流程编排、数据处理与转换、规则引擎与决策逻辑、接口与集成设计、状态机与调度机制、性能优化与缓存策略、安全与权限控制等（依项目领域灵活识别） |
| 4 | 系统设计文档 | 系统设计、架构说明、模块划分、数据流与控制流 |

## 扫描目标目录模版

执行时按项目实际目录填写：

```
[项目根目录]/
├── [专利或文档目录]/     ← 专利点分析、交底书、申报建议
├── [设计文档目录]/       ← 详细设计、方案讨论、流程图、技术对比
├── [代码目录]/           ← 算法实现、业务逻辑、规则引擎、接口与集成、调度机制等
└── [根目录]/             ← 系统设计、架构说明、模块与数据流
```

## 执行提示

- 大仓库先用搜索 / 语义检索定位关键文件，再精读。
- 记录**引用路径或文件名**，便于在交底书中写「参见某设计」时脱敏表述。
- 凡出现 **`.docx` / `.pptx`**，**必须**按下一节 **「Office 文档」** 先转 Markdown 再读，不可跳过或只扫纯文本而漏掉 Office。
- 凡扫描树内可能有 CAD / 三维文件，**必须**按 **「CAD / STEP（可选，默认关闭）」** 执行分类；**不得**在用户未确认时安装 STEP 依赖或运行 `step_to_views.py`。

## CAD / STEP（可选，默认关闭）

**开关**：STEP 多视角解析 **默认关闭**。仅当用户回复 **是**（或明确肯定）后，才可延迟安装依赖并转换；回复 **否** 则跳过解析。

**分类扫描（轻量，无重依赖）**：在扫描根（含 `knowledge/`、用户 @ 的目录等）执行：

```bash
python ${CLAUDE_SKILL_DIR}/tools/shared/cad_scan.py -r "<扫描根>" --json
```

（多根可重复 `-r`。初次 Step 2 与**多轮补材料后**均须再跑。）

依据 JSON 的 `action`：

| `action` | 行为 |
|----------|------|
| `ask_enable_step_parse` | **立即中断**后续挖点/成文；展示 `step_files`，反问是否开启（请用户回 **是** / **否**）。未得 **是** 前禁止装依赖与 `step_to_views.py`。 |
| `hint_export_step` | **不中断**扫描（继续 Office/文档/图片流程）；在**本轮对话回复末尾**提示：可将原生 CAD 导出为 `.step`/`.stp` 后再开启解析（文案可用 JSON `messages.hint_export_step`）。 |
| `none` | 无 CAD 相关文件，忽略。 |

**用户回复「是」后**：

```bash
pip install -r ${CLAUDE_SKILL_DIR}/tools/shared/requirements-step.txt
python ${CLAUDE_SKILL_DIR}/tools/shared/step_to_views.py --check-deps
python ${CLAUDE_SKILL_DIR}/tools/shared/step_to_views.py --enable-step-parse \
  -i "<path/to/model.step>" -o "outputs/{案件标识}/cad_views"
```

- 产出：`views/*.png`（iso/front/top/right）、`assembly_tree.yaml`、`structure_schema.seed.yaml`、`figure_plan.seed.yaml`。  
- 随后按 `prompts/shared/fill_structure_schema.md`：**审改** seed → 定稿 `structure_schema.yaml` + `figure_plan.yaml`（自动视图已预填 `assembly` + `alternate_view` 的 `relates_to`；仍须补 `covers` / 主题 / 局部图）。  
- **禁止**无 `--enable-step-parse`（且无环境变量 `PATENT_SKILL_STEP_PARSE=1`）时强行转换。  
- 用户回复 **否**：记录决定，继续仅用已有图片/文档；可在回复末尾保留「日后可导出 STEP 再开」一句。

**后缀**：`.step`/`.stp` 为可解析目标；原生 CAD（`.sldprt`/`.sldasm`/`.ipt`/`.iam`/`.prt`/`.asm`/`.catpart`/…）见 `tools/shared/cad_formats.py`，**本技能不直接解析**。

## 外观辅助线稿（可选，默认关闭）

仅**外观设计**且材料中**已有产品图**时适用。细则：`prompts/shared/design_lineart_assist.md`。

- **默认关**；可反问是否开启（**是** / **否**）。文案：`python tools/shared/design_lineart_gate.py --print-confirm`。
- 用户 **是**：先填 Appearance + figure_plan → 写 `design_lineart_brief.yaml`（读 YAML + 多视 `relates_to`）→ `design_lineart_gate.py --enable-design-lineart --prepare-jobs` → **带参考图**出线稿。
- **无图**或用户未确认：**禁止**生成线稿；**禁止**纯文生图。
- 辅助线稿默认不入交底正文（`use_in_disclosure: false`）。

## 实用新型结构辅助线稿（可选，默认关闭）

仅**实用新型**且材料中**已有结构相关图**时适用。细则：`prompts/shared/structure_lineart_assist.md`。

- **默认关**；可反问是否开启（**是** / **否**）。文案：`python tools/shared/structure_lineart_gate.py --print-confirm`。
- 用户 **是**：先填 Structure + figure_plan → 写 `structure_lineart_brief.yaml`（件号对齐 `parts`）→ `structure_lineart_gate.py --enable-structure-lineart --prepare-jobs` → **带参考图**出轮廓；序号层推荐 **overlay**（按部件表叠引出线，禁止自创件号）。
- **无图**或用户未确认：**禁止**；**禁止**纯文生图。勿与 `design_lineart_*` 混用。
- 辅助线稿默认不入交底正文（`use_in_disclosure: false`）。

## Office 文档（.docx / .pptx）：必先转换再读

**格式**：脚本仅支持 OOXML（**`.docx` / `.pptx`**）。旧版 **`.doc` / `.ppt`** 须先在 Office / WPS 中**另存为**新格式后再走下列流程。

Agent **不得**因「只能舒适读取文本」而**遗漏**项目内的 Word / PPT：**必须先转为 Markdown 再纳入扫描**，不能只扫 `.md` 与源码。

1. **发现**：在扫描目录内 **`Glob` 或列举** `*.docx`、`*.pptx`（含子目录，如 `docs/sample_*.docx`）。
2. **转换（本仓库脚本）**：对每个文件执行（路径按实际替换；`${CLAUDE_SKILL_DIR}` 为技能根）：

   ```bash
   python ${CLAUDE_SKILL_DIR}/tools/shared/docx_to_md.py -i "<路径>/<名>.docx" -o "<同目录或 docs>/<名>.md"
   python ${CLAUDE_SKILL_DIR}/tools/shared/pptx_to_md.py -i "<路径>/<名>.pptx" -o "<同目录或 docs>/<名>.md"
   ```

   需已 `pip install -r requirements.txt`。输出旁会生成 **`{md 主名}_media/`**，内为嵌入图，**以生成的 `.md` 正文与图片引用为扫描依据**。
3. **再读**：**`Read`** 上述新生成的 `.md`（及必要时扫一眼 `_media` 文件名用于脱敏引用），与原有 `.md`、代码**同等对待**，摘要进专利点材料表。
4. **解析重点**：表格、编号列表、**PPT 每页标题与正文**、**Word 修订区以外的正文**、**备注**（`pptx_to_md` 会写入「备注」小节）——均属可专利化叙述来源。

## 图片与裸图目录（跳过单独识图）

- **`sample_assets/`** 等目录下的 **独立 `.png` / `.jpg` / `.webp` 等**：**不作为** Step 2 必须逐个打开、OCR 或描述的对象（与 Word/PPT 内嵌图**通常重复**时更不必重复读图）。
- **例外**：用户**点名**某图片路径，或某图**未**出现在任何已转换 Office 的 `_media` 中且对专利点明显关键时，再按需处理。
- Word/PPT 转换后，嵌入图已在 **`![](相对路径)`** 中体现，**以 Markdown 文本扫描为主**即可。

## 按专利类型加扫（实用 / 外观）

当前类型为**实用新型**或**外观设计**时，在通用优先级之外**额外**关注：

| 类型 | 加扫重点 |
|------|----------|
| 实用新型 | 装配图、爆炸图、结构说明、`structure_*.yaml/json`、零件表；再按 `shared/fill_structure_schema.md` 识图填表并写出 **`figure_plan.yaml`** |
| 外观设计 | 六视/立体图、效果图、色彩说明、`appearance_*.yaml/json`；再按 `shared/fill_appearance_schema.md` 填表并写出 **`figure_plan.yaml`** |

独立结构/外观附图（用户点名或 schema `source_images`）**需要** Read 识图，不适用下方「sample_assets 跳过」惯例。

## 示例案件 `knowledge/`（练习时勿漏）

### 发明 · `examples/example_batch_job_scheduler/knowledge/`

| 路径 | 动作 |
|------|------|
| `docs/architecture.md` | 直接 Read |
| `docs/sample_architecture_review.docx` | **先** `tools/shared/docx_to_md.py` → 再 Read 生成的 `.md` |
| `docs/sample_scheduler_deck.pptx` | **先** `tools/shared/pptx_to_md.py` → 再 Read 生成的 `.md` |
| `docs/sample_assets/*.png` | **跳过**单独精读（内容已由 Office 内嵌图 + 转换 MD 覆盖） |

### 实用新型 · `examples/example_utility_model_snap_heatsink/knowledge/`

| 路径 | 动作 |
|------|------|
| `docs/structure_brief.md` | Read |
| `assets/*.png` | **须**识图填 StructureSchema + **`figure_plan.yaml`**（教学用；勿依赖预填 yaml；优先线稿/结构图入文） |
| `cad/demo_snap_plate.step` | **cad_scan** → `ask_enable_step_parse`（默认关；确认后才 `step_to_views`；教学几何非真实产品） |

### 外观 · `examples/example_design_desk_lamp/knowledge/`

| 路径 | 动作 |
|------|------|
| `docs/design_brief.md` | Read |
| `assets/*.{jpg,png}` | **须**识图填 AppearanceSchema + **`figure_plan.yaml`**（教学用；勿依赖预填 yaml；场景图默认低优先级） |
