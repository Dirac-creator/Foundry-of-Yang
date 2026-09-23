# 首次提交到 GitHub

在 VS Code 打开此仓库，菜单「终端 → 新建终端」，确认终端位于仓库根目录。

```powershell
.\.venv\Scripts\python.exe -m foundry validate examples/demo_dataset.json
.\.venv\Scripts\python.exe -m pytest
git status
git add README.md CONTRIBUTING.md .gitignore .gitattributes pyproject.toml docs src examples tests .github
git diff --cached --stat
git commit -m "建立基础框架和工艺数据规范"
git push origin main
```

提交前查看 VS Code 源代码管理中的文件差异。暂存列表不应包含 `.venv`、密码或真实实验数据。Commit 保存本地历史，Push 同步到 GitHub。推送时保持 Clash Verge 运行；若 GitHub 提示登录，使用自己的账号。

如果 main 已受保护，在 git add 之前执行 `git switch -c feature/project-foundation`，最后改为 `git push -u origin feature/project-foundation`，再在 GitHub 创建 PR。

推送后在 GitHub Actions 页面确认 checks 通过；本地测试通过不等于远程检查已经运行。
