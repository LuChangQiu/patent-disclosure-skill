# AppearanceSchema 填写（图 / 原文 → 外观事实）

**合同**：`references/schemas/appearance.schema.yaml`  
**附图选用**：`references/schemas/figure_plan.schema.yaml`（交底必做）  
**消费者**：交底 `disclosure/design/`；解读 `reader/`（外观设计）

## 何时 Read

- 交底类型为**外观设计**  
- 解读对象为外观设计专利  

## 落盘目录（交底）

默认 **`outputs/{案件标识}/`**。同目录写出：

| 文件 | 说明 |
|------|------|
| `appearance_schema.yaml`（或 `.json`） | AppearanceSchema 实例 |
| `figure_plan.yaml` | 入文视图选用、排序与**视图关联** |

`figure_plan.schema_ref` 填**本实例**（如 `appearance_schema.yaml`），勿填合同路径。

## 流程

1. 收集六视图 / 立体图 / 效果图 / 专利视图  
   - 若有 STEP 且用户已确认开启：可用 `step_to_views.py` 自动投影作视图材料（外观仍以可见造型为准；场景图规则不变）。  
2. **跨图联读**：多视视为同一产品；比例、开口、装饰位置须一致；矛盾写入 `uncertain`  
3. 先填 AppearanceSchema，再写交底提纲或通俗笔记  
4. **交底模式**：**`Write`** `appearance_schema.yaml`（或 json）**与** `figure_plan.yaml`  
   - `covers` 对齐 `views.name` 或设计要点短标签  
   - 多视之间可用 `relates_to`：`same_state` / `alternate_view`；局部造型用 `detail_of` 指向立体/主视  
   - `views[].source_image` 可选，指向材料路径  
   - **优先**产品区清晰的立体/正交（`photo_clean` 或线稿均可）；重场景/包装默认 `reference` 或不入文  
   - 外观**不强制**线稿；缺正式六视写入 AppearanceSchema `uncertain`  
   - `theme_summary` = 当前产品外观主题；`patent_type: design`  
5. **辅助线稿（可选，默认关）**：材料中**已有图片**时，可反问是否开启（**是** / **否**）。用户回 **是** 后 **`Read`** `prompts/shared/design_lineart_assist.md`：先写 `design_lineart_brief.yaml`（读 appearance + figure_plan，联读 `relates_to`），再 `design_lineart_gate.py --enable-design-lineart --prepare-jobs`，**仅**带参考图出线稿；无图禁止本流程与纯文生图。辅助线稿默认 `use_in_disclosure: false`。  
6. **解读模式**：工作目录 **`appearance_schema.json`**；`figure_plan` **可选**  
7. 区分「整体造型」与「装饰图案/色彩」；`uncertain` 单独列出  
8. `mode`：`disclosure` | `reader`

## 多轮

换图、改产品侧重点或设计要点时：**无则新建、有则重评** `figure_plan.yaml`（含 `relates_to`），再改正文视图引用。

## 最低输出

- AppearanceSchema 实例：含 `overall_shape`、`views`（或 `uncertain` 说明缺图）、`ornament`/`color` 可空、`uncertain`  
- 交底另须：同目录 **`figure_plan.yaml`**
