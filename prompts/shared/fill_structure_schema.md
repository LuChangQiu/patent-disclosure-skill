# StructureSchema 填写（图 / 原文 → 结构事实）

**合同**：`references/schemas/structure.schema.yaml`  
**附图选用**：`references/schemas/figure_plan.schema.yaml`（交底必做）  
**消费者**：交底 `disclosure/utility_model/`；解读 `reader/`（实用新型或装置附图）

## 何时 Read

- 交底类型为**实用新型**，或发明案中需写清装置结构  
- 解读对象为实用新型，或附图以装配/结构为主  

## 落盘目录（交底）

默认 **`outputs/{案件标识}/`**（与交底定稿同级）。同目录写出：

| 文件 | 说明 |
|------|------|
| `structure_schema.yaml`（或 `.json`） | StructureSchema 实例 |
| `figure_plan.yaml` | 入文附图选用、排序与**图际关联** |

`figure_plan.schema_ref` 填**本实例**相对路径（如 `structure_schema.yaml`），勿填合同文件 `references/schemas/structure.schema.yaml`。

## 流程

1. 收集结构图（照片、CAD 截图、爆炸图、专利附图）  
   - 若存在 **`.step`/`.stp`** 且用户已确认开启解析：先按 `project_scan.md`「CAD / STEP」运行 **`step_to_views.py --enable-step-parse`**，以产出的 `views/*.png` + `*.seed.yaml` 为材料起点（**默认不开启、不装依赖**）。  
   - 仅有原生 CAD、无 STEP：勿假装已解析；提示用户导出 STEP（见 `cad_scan.py`）。  
2. **跨图联读**：总装 / 爆炸 / 局部须对照同一套件号；先建立「图角色」再填 parts（禁止每张图各起一套命名）  
3. 先填 StructureSchema，再写交底/笔记；禁止看图直接长文  
4. **交底模式**：在上表目录 **`Write`** `structure_schema.yaml`（或 json）**与** `figure_plan.yaml`  
   - 若有 `figure_plan.seed.yaml` / `structure_schema.seed.yaml`：可复制审改为定稿，**须**人工核对件名、`covers`、主题；自动 `relates_to`（`alternate_view`）可保留。  
   - 对每张候选图判定 `role` / `kind` / `covers`（对齐 `parts.id`）/ `score`  
   - **图际关联**：局部/剖视/爆炸图填写 `relates_to`（如 `detail_of` → 总装 `fig`）；有 assembly+detail 入文对时**不得**漏写  
   - 可选：关键 `relations[].seen_in` 列出能看见该连接的 `fig` 号  
   - **优先** `lineart`、`cad`；场景杂图默认不入文  
   - 仅 `use_in_disclosure: true` 分配连续 `fig`（1…N）  
   - `theme_summary` 写当前结构主题；`patent_type: utility_model`  
5. **辅助线稿（可选，默认关）**：材料中**已有结构相关图**且缺干净线稿/CAD 时，可反问是否开启（**是** / **否**）。用户回 **是** 后 **`Read`** `prompts/shared/structure_lineart_assist.md`：先写 `structure_lineart_brief.yaml`（读 Structure + figure_plan，件号对齐 `parts`），再 `structure_lineart_gate.py --enable-structure-lineart --prepare-jobs`，**仅**带参考图出轮廓；序号层推荐 `callout_mode: overlay`（按 `parts` 叠引出线，禁止模型自创件号）。无图禁止。辅助线稿默认 `use_in_disclosure: false`。勿与外观 `design_lineart_*` 混用。  
6. **解读模式**：工作目录 **`structure_schema.json`**（入库脚本约定名）；`figure_plan` **可选**，不强制；若写 figure_plan 仍建议补 `relates_to`  
7. `uncertain` 不得写成确定保护点；跨图对不上的写入 `uncertain`  
8. `mode`：`disclosure` | `reader`

## 多轮

原材料增删换、主题/候选点变更、新增局部图时：**无清单则新建、有则重评** `figure_plan.yaml`（含 `relates_to`），再改交底附图与「如图 N」。细则见 figure_plan 合同「多轮同步」。

## 最低输出

- StructureSchema 实例：合法 JSON/YAML，含必填 `parts`、`relations`（或显式 `[]` + 说明）、`spatial`、`uncertain`  
- 交底另须：同目录 **`figure_plan.yaml`**（可无入文图，但须条目说明原因；有总装+局部则须 `relates_to`）
