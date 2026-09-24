# 数据规范 v1.0.0

机器可读定义：`src/foundry/schemas/dataset.schema.json`。所有交换文件使用 UTF-8 JSON，顶层 `schema_version` 为 `1.0.0`。未知字段拒绝，防止拼写错误被静默忽略。

## 标识和关联

记录 ID 是稳定、区分大小写的字符串，允许英文字母、数字、点、下划线及短横线。推荐格式：`LOT-20260923-001`、`WAF-001`、`DIE-001`、`DEV-001`、`RUN-001`、`MEA-001`、`LAY-001`、`FILE-001`。同一数据集中所有实体 ID 不重复；多人新建数据前由课题组分配编号段。不要使用文件名或数组顺序代替关联 ID。

| 集合 | 关键字段 | 语义 |
|---|---|---|
| samples | id, kind, parent_id | lot → wafer → die → device；批次无父级，其余必须引用正确层级 |
| layouts | id, revision, artifact_id | 版图版本及文件；修改版图新增记录 |
| process_runs | id, sample_id, process_type, recipe_id, recipe_version, equipment_id, started_at, ended_at, parameters | 一次真实执行；重复刻蚀需两个 run，不能覆盖 |
| measurements | id, sample_id, process_run_id, measured_at, method, instrument_id, quantities, conditions | 一次实测；process_run_id 为 null 表示未关联特定工艺 |
| artifacts | id, uri, sha256 | 原始文件位置及内容指纹；跨电脑共享时避免本机盘符 |

样品可通过 `layout_id` 关联版图；芯片、器件可通过 `position` 保存相对父级的位置。position 必须声明 reference、x、y、unit，不能默认推断坐标原点或轴方向。

工艺的 `previous_run_ids` 表示显式前序依赖，必须无环且前序完成不晚于当前开始。允许晶圆加工后在其下属芯片、器件上继续加工；引用的前序样品只能是当前样品或祖先。工艺类型为 annealing、deposition、etching、cleaning、lithography、other。

测量可关联当前样品或其祖先样品上的工艺（例如器件测试引用晶圆刻蚀），测量时间不得早于该工艺结束。若是工艺前测量，应引用前一个工艺或 null。一条测量只保存一个主要工艺关联，不意味着测试结果仅受这一工艺影响。

## 数值与单位

每个参数或观测量使用 `{ "value": 100, "unit": "nm" }`。value 必须为有限数字；缺失不写，不能用 0 代替。可选 `uncertainty` 为非负值，与 value 同单位；具体置信定义应在测量方法说明中记录。

v1 标准单位：长度 nm，时间 s，温度 K，压力 Pa，流量 sccm，功率 W，角度 deg，损耗 dB，损耗系数 dB/cm，波长 nm，无量纲 1。导入程序负责转换，并保留原始文件。校验器对已知字段强制单位，例如 etch_depth/thickness/wavelength 为 nm，duration 为 s，temperature 为 K。自定义字段只能使用 Schema 单位枚举，物理含义须先在 PR 文档中定义。

时间使用带时区的 RFC 3339，例如 `2026-09-23T10:00:00+08:00`。记录创建者使用 `operator`；它是署名，不替代系统权限或审计。

`conditions` 使用相同数值与单位格式，保存温度、波长等数值测试条件。`method` 写明测量方法和必要的非数值条件（例如 TE 偏振）。有原始文件时使用 `artifact_ids` 关联。

## 版本与修改

- `schema_version` 描述交换格式，不是软件版本或配方版本。
- 改动字段含义、单位或必填规则必须升级 Schema 并提供迁移说明，不能静默解释旧数据。
- 原始数据不覆盖。测量更正新增记录，通过 `supersedes_id` 指向同一样品的旧测量，保留历史；本版校验更正链无环。
- 示例中数据全部虚构，只用于校验演示；文件引用允许为空，不伪造真实文件或校验和。
- 预测结果与实测分开；未来模型输出使用 `docs/module-api.md` 中的独立运行记录。

## 当前校验边界

可校验结构、ID、引用、样品层级、时间顺序、单位和有限数值；不能证明实验真实性、模型准确性、设备允许范围或外部文件可达性。v1 不表达样品合批、多父级谱系或完整设备配方；需要时通过规范变更增加。

## v0.2.0 表单录入

新增的服务录入格式与本完整交换格式分开版本管理，详见 [共享数据库说明](shared-database.md)。表单可保留缺失设备或配方的信息，不自动伪造数据以满足此处的必填字段。
