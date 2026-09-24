# Foundry-of-Yang

集成光子学 foundry 工艺数据与仿真协作平台。

当前版本：0.4.0，支持 GitHub 仓库存储和本机数据库两种模式。提供统一网页表单、集中 SQLite 存储、成员令牌与只读/录入权限、工艺分类、单位换算、历史更正、附件上传下载、查询和备份。保留 v1 JSON 数据校验工具；尚未实现物理仿真、自然语言识别、日志内容解析或批量导入。

## 多人共享：GitHub 模式

静态网页直接访问 GitHub，工艺记录和附件保存在本仓库的 `foundry-data` 分支，你的电脑关机不影响其他人使用。每位成员使用自己的 GitHub 令牌；本仓库为公开仓库，只上传允许公开的数据。

[多人使用和令牌配置](docs/github-storage.md)。Pages 地址：`https://dirac-creator.github.io/Foundry-of-Yang/`，需要 Pages 工作流完成部署。

## 打开本机工艺录入工作台

首次安装依赖后，在 Windows 双击仓库根目录的 `start-local.cmd`，保持窗口运行，打开 http://127.0.0.1:8000 。个人令牌保存在 `.local/local-user-token.txt`，复制到页面登录框。此地址只供本机使用。

[详细操作及多人共享说明](docs/shared-database.md)

## 快速开始（Windows PowerShell）

安装 Python 3.11 或以上版本后，在本仓库根目录打开终端：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -m foundry validate examples/demo_dataset.json
.\.venv\Scripts\python.exe -m pytest
```

如果没有 `py` 命令，请使用已安装的 Python 解释器完整路径替代 `py -3`。无需激活虚拟环境。校验成功时输出记录数量；失败时返回非零退出码。

## 目录

- `src/foundry/`：公共数据校验、工艺模块、流程编排和光学分析。
- `src/foundry/service/`：表单、API、参数字典和集中数据库。
- `src/foundry/schemas/`：随软件发布的机器可读数据规范。
- `docs/`：架构、数据规范、模块接口和后续任务。
- `examples/`：可公开提交的虚构小型数据。
- `tests/`：格式、单位和关联一致性测试。
- `.github/`：PR、Issue 模板及自动检查。

## 阅读顺序

1. [数据规范](docs/data-model.md)
2. [总体架构](docs/architecture.md)
3. [模型接口约定](docs/module-api.md)
4. [协作规范](CONTRIBUTING.md)
5. [首阶段任务](docs/roadmap.md)
6. [首次提交操作](docs/first-submit.md)

本机模式的原始数据保存在仓库外，或本地被忽略的 `data/raw/` 中。GitHub模式将允许公开的数据写入专用分支。原始数据保留不覆盖。不要提交账号密码、设备密钥或未经许可公开的版图。

本项目尚未选定开源许可证；仓库公开可见不等于授予开源使用许可，发布前由课题组确认许可证与数据公开范围。
