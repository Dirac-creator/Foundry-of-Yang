> v0.4.0 已增加不依赖本机在线的 [GitHub存储模式](github-storage.md)。以下说明仍适用于本机数据库模式。

# 统一表单与共享数据库 v0.3.0

## 现在如何使用

本次选择在个人电脑验证，服务默认只监听 `127.0.0.1:8000`。无需云服务器或 Docker。

1. VS Code 打开仓库根目录，初次运行按 README 安装 `.[dev,server]` 依赖。
2. 双击仓库中的 `start-local.cmd`。脚本自动进入仓库目录；首次创建 local-user（录入权限），生成个人访问令牌文件，随后启动服务。
3. 保持命令窗口运行，浏览器打开 `http://127.0.0.1:8000`。
4. 打开 `.local/local-user-token.txt`，复制令牌到页面并连接。令牌不是 GitHub 密码。
5. 先登记批次（如 LOT-20260924-001），再登记晶圆（如 WAF-001，并选择所属批次）。芯片和器件按需登记。
6. 在统一表单选择样品、工艺类型、实际开始时间，填写参数及单位，保存。
7. 下方列表按时间倒序展示，可按样品、工艺筛选；原始参数、录入人、原始时间和备注可展开查看。

工艺类型切换会提供推荐参数行；未填参数不保存，不自动填充实验值。至少填写一个参数。设备、配方和备注选填，鼓励真实记录时补齐。开始时间采用操作者电脑本地时区，服务端保存 UTC 时间。

例如：选择退火，输入 30 min 和 400 °C，保存后标准参数为 1800 s 和 673.15 K，同时保留原单位。选择长膜时“目标膜厚”仅代表工艺目标，不能替代实测膜厚。材料、气氛、溶液浓度、升温程序等目前可写备注；需要结构化查询的字段应通过代码评审加入参数字典。

## 共享方式

```text
成员A浏览器 ─┐
成员B浏览器 ─┼─ 同一个服务接口 ─ 服务电脑本地数据库
成员C浏览器 ─┘
```

此版可为小型课题组提供统一服务和并发请求，成员使用不同令牌访问同一份数据。已登录成员均可查看全部记录；reader 只读，editor 可登记样品、新增工艺并更正记录。不提供按项目隔离权限。GitHub 仓库协作者权限不会自动变成数据库访问权限。

管理员在服务电脑上创建成员：

```powershell
.\.venv\Scripts\python.exe -m foundry.service add-user member1 --role editor --token-file .local/member1-token.txt
.\.venv\Scripts\python.exe -m foundry.service add-user viewer1 --role reader --token-file .local/viewer1-token.txt
```

每人分发自己的令牌；不要共享 local-user。令牌在数据库中仅存 SHA-256，明文文件用于首次分发并由管理员妥善保管，不进入 Git。更换令牌可使旧令牌立即失效：

```powershell
.\.venv\Scripts\python.exe -m foundry.service rotate-user member1 --token-file .local/member1-new-token.txt
```

实际跨电脑开放前，应选定持续运行的主机、访问网络及备份负责人。将服务置于 HTTPS 反向代理后，或通过 SSH 加密隧道访问回环地址；普通 HTTP 会明文传输令牌，不直接开放公网。当前没有改动电脑防火墙，没有启用外网访问。`serve --host 0.0.0.0` 可作为受控网络部署配置，但不应单独视为已完成安全部署。

SQLite 文件仅放在运行服务的同一台主机的本地磁盘，不放网盘、SMB 共享目录，也不让各成员直接打开数据库。服务器串行执行写事务，WAL 支持并发读取；这适合初期小团队验证。大量并发写入、多实例或多项目隔离时，应迁移 PostgreSQL 并扩展权限。

## 数据和备份

- 正式本机数据：`data/local/foundry.sqlite3`（以及运行时的 -wal / -shm 文件）。
- 本次 UI 验证数据：`.local/ui-test.sqlite3`，与正式数据库完全分离。
- 凭据：`.local/`。
- 所有这些本地文件已在 `.gitignore` 排除；提交代码不会备份实验数据库。

运行期间使用 SQLite backup API 创建一致性备份，不只复制单独的数据库主文件：

```powershell
.\.venv\Scripts\python.exe -m foundry.service backup backups/foundry-20260924.sqlite3
```

目标文件必须不存在。按实际日期取新名字，将备份另存到受控存储位置。恢复时先停止原服务，以备份文件启动验证：

```powershell
.\.venv\Scripts\python.exe -m foundry.service --database backups/foundry-20260924.sqlite3 serve --port 8001
```

备份也包含账号令牌哈希。不要公开备份；恢复旧备份可能恢复旧令牌状态，必要时轮换成员令牌。

## API 与版本关系

所有 `/api/*` 路由要求 `Authorization: Bearer <个人令牌>`。前端和未来设备导入器使用相同的写入接口。

| 接口 | 用途 |
|---|---|
| GET /api/me | 当前成员及权限 |
| GET /api/catalog | 工艺分类、参数和允许单位 |
| GET /api/samples | 样品目录 |
| POST /api/samples | 登记样品并检查父子层级 |
| POST /api/records | 新增或更正工艺记录 |
| GET /api/records | 分页查询，支持 sample_id、process_type、include_history、limit、offset |

写入使用 submission_id 做幂等控制：同一成员重复提交相同编号和内容返回同一记录；同编号不同内容返回 409。正式记录 ID 由服务器生成，作者取认证身份，调用方不能伪造。更正使用 supersedes_id，旧记录保留；默认查询只显示当前版本，include_history=true 可查询全部。

数据库 user_version=2（启动时自动从1升级，保留已有样品和工艺记录）；工艺录入 payload 的 capture_version=1.0.0。它与旧 `schema_version=1.0.0` 的完整交换数据集不同：表单允许缺少设备、配方版本和结束时间，不伪造这些信息。因此当前不直接导出为旧交换格式；后续需要显式字段补齐与转换，并经过原校验器。两者共享样品层级和单位语义。

参数的规范由 `service/models.py` 的 PARAMETERS 定义。缺少某个实验参数时，先提交字段名称、单位和物理含义，通过评审后扩展；不把未知参数默认为另一种量。

## 当前范围

已实现工艺记录表单、集中存储、身份及角色、记录更正、单位换算和备份。尚未实现实测数据独立录入、Excel 批量导入、日志内容解析、模型仿真或自动推断工艺因果链。工艺时间排序不是前序依赖的替代。下一步应根据真实数据样例扩展参数和测量入口。


## 设备日志附件（v0.3.0）

- 新建记录：在“设备日志与其他附件”选择一个或多个文件，再保存工艺。
- 已有记录：在记录行点击“附件”，选择文件并点击“上传附件”。
- 查看与下载：附件列表显示原文件名、大小、上传人、时间和 SHA-256，可点击“下载”取回原文件。
- ZIP、CSV、LOG、REC、RCP 以及其他原始文件均按字节保存，不解压、不自动解析、不执行。单文件限 50 MiB，空文件拒绝。
- 字节内容保存在 SQLite 的 attachments.content BLOB 中，并通过 record_id 关联具体工艺执行，不仅仅关联样品。现有数据库备份命令包含全部附件。
- 同一工艺记录、相同文件名、相同 SHA-256 的重复上传返回已有附件；同名不同内容保留为两个独立文件，不覆盖。
- 工艺更正后可看到该记录及所有前序版本的附件，列表会标明来自更正前版本。新增补传文件仅关联所选版本。
- 所有成员可查看下载；只有 editor 可上传。文件不使用公开下载链接，下载仍校验个人令牌。
- 工艺记录和每个附件分别提交。若部分上传失败，已成功的文件与工艺记录仍保留；在该记录附件区重新选择失败文件补传，不要重复创建工艺。
- 本轮示例 ZIP 仅上传到独立测试数据库，未自动绑定正式工艺。

附件接口：

| 接口 | 作用 |
|---|---|
| POST /api/records/{record_id}/attachments?filename=URL编码文件名 | 请求体为原始文件字节，Content-Type: application/octet-stream |
| GET /api/records/{record_id}/attachments | 返回当前及前序更正版本附件元数据，不返回文件内容 |
| GET /api/attachments/{attachment_id}/download | 认证后下载原始内容 |

附件会增加数据库和备份体积。此版本适合小团队本机试用；大量大文件需要在后续版本迁移到统一文件/对象存储，并保留数据库中的关联和校验值。
