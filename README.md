# Foundry-of-Yang

集成光子学 foundry 工艺数据与仿真协作平台。

当前版本：0.1.0 基础框架。已提供数据规范、JSON Schema、关联校验、虚构示例和自动化测试；尚未实现物理仿真、参数推荐、数据库或图形界面。

## 快速开始（Windows PowerShell）

安装 Python 3.11 或以上版本后，在本仓库根目录打开终端：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m foundry validate examples/demo_dataset.json
.\.venv\Scripts\python.exe -m pytest
```

如果没有 `py` 命令，请使用已安装的 Python 解释器完整路径替代 `py -3`。无需激活虚拟环境。校验成功时输出记录数量；失败时返回非零退出码。

## 目录

- `src/foundry/`：公共数据校验、工艺模块、流程编排和光学分析。
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

真实实验数据保存在仓库外，或本地被忽略的 `data/raw/` 中。原始数据保留不覆盖。不要提交账号密码、设备密钥或未经许可公开的版图。

本项目尚未选定开源许可证；仓库公开可见不等于授予开源使用许可，发布前由课题组确认许可证与数据公开范围。
