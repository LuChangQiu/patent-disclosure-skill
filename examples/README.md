# 示例案件目录

本目录提供**可随仓库提交的演练材料**。

| 路径 | 类型 | 说明 |
|------|------|------|
| `example_batch_job_scheduler/` | **发明**交底 | 虚构「批任务调度」；`knowledge/` 供 Step 2 扫描 |
| `example_utility_model_snap_heatsink/` | **实用新型**交底 | 卡扣散热结构教学 brief；真实专利附图 + 教学用 `knowledge/cad/*.step`（测 STEP 反问/解析） |
| `example_design_desk_lamp/` | **外观设计**交底 | 折臂台灯教学 brief；国内媒体实拍 + README 下载链接 |
| `example_patent_reader/` | **解读** | README 内 CDN / `fetch_patent_pdf` 下载链接；PDF 本地自备（gitignore） |

冒烟用极简 TXT 见 `tests/fixtures/patent_reader_sample.txt`。

---

## 实用新型交底演练

见 [example_utility_model_snap_heatsink/README.md](example_utility_model_snap_heatsink/README.md)。

要点：intake 指定「实用新型」→ 填 StructureSchema + **`figure_plan.yaml`** → `prompts/disclosure/utility_model/` 成文（只嵌清单入文图）→ 查新 `--type utility_model`。  
可选：`cad_scan.py` 应发现 `knowledge/cad/demo_snap_plate.step` 并反问是否开启 STEP 解析（默认关）。

## 外观设计交底演练

见 [example_design_desk_lamp/README.md](example_design_desk_lamp/README.md)。

要点：指定「外观设计」→ AppearanceSchema + **`figure_plan.yaml`** → `prompts/disclosure/design/` → 查新 `--type design`。

## 专利解读（含实用 / 外观 PDF）

见 [example_patent_reader/README.md](example_patent_reader/README.md)。实用新型 / 外观公开号下载后，解读时按 `type_hooks.md` 写 `structure_schema.json` / `appearance_schema.json`，入库自动写入笔记与 Canvas。

## 发明交底（原有）

### 如何使用 `example_batch_job_scheduler`

全流程产物由技能写入 **`outputs/{案件标识}/`**。命名见 **`prompts/disclosure/invention/disclosure_builder.md` §7.3**。

#### 方式 A：只看原材料

打开 `example_batch_job_scheduler/knowledge/`。

#### 方式 B：Agent 全流程

```text
请按 patent-disclosure-skill 全流程执行：
- 项目扫描目录：examples/example_batch_job_scheduler/knowledge/
- 技术主题：分布式批任务调度、异构集群、资源感知与限频重排队
```

（未指定类型时**默认发明**。）

查新见 `prompts/disclosure/prior_art_search.md`。定稿经 `tools/shared/mermaid_render.py`。

#### 迭代

`prompts/disclosure/iteration_context.md` + `merger.md` / `correction_handler.md`。
