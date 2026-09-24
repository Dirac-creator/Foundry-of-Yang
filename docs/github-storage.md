# GitHub 仓库存储与多人网页访问

## 本项目的选择

使用公开仓库 `Dirac-creator/Foundry-of-Yang`。软件位于 main，工艺数据位于 foundry-data 分支。用户已选择保留公开仓库，因此只录入允许公开的参数与附件。即使网页要求令牌，公开仓库中的数据仍可被任何人读取。

发布后的网页地址为 `https://dirac-creator.github.io/Foundry-of-Yang/`（以 Pages 实际发布结果为准）。这是静态网页，直接调用 GitHub API；访问和上传不依赖原作者电脑，也不需要 Python 服务在线。

## 每位成员如何连接

1. 成为该仓库的协作者并接受邀请；有写入权限才能保存。
2. 在自己的 GitHub 账号创建访问令牌，不使用工作台以前的 local-user 令牌，也不要借用别人的令牌。
3. 打开网页，选择 GitHub 仓库模式。
4. 仓库填写 `Dirac-creator/Foundry-of-Yang`，数据分支填写 `foundry-data`。
5. 粘贴个人 GitHub 令牌，点击连接。确认公开可见性后，登记样品、录入工艺并上传附件。

仓库所有者可使用 fine-grained PAT，仅选择此仓库，并授予 Contents: Read and write。GitHub 的 fine-grained PAT 对个人仓库外部协作者可能有限制；若成员无法选择此仓库，可对当前公开仓库使用 classic PAT 的 `public_repo` scope。该 scope 可操作此成员有权写入的其他公开仓库，并非只限本项目，应设置短期有效期。组织成员也需遵守组织审批/SSO规则。

令牌只在当前页面内存中保留，不写入仓库、浏览器本地存储或 URL。刷新网页后需重新输入。不要把令牌发在聊天、Issue 或代码里。GitHub 权限和令牌权限共同决定实际可用操作；写入被拒绝时页面显示错误。读取数据本身也消耗 GitHub API 配额。

## 保存内容

首次保存会创建 foundry-data 分支，之后每次操作生成 Git 提交。结构如下：

```text
index.json                         # 查询索引，包含元数据
samples/<样品编号>.json
records/<工艺记录编号>.json
attachment-metadata/<附件编号>.json
attachments/<工艺记录编号>/<附件编号>/<原文件名>
```

数据分支不运行 main 上的 CI 或 Pages 工作流。代码更新与数据录入各自提交；网页刷新会读取数据分支最新提交，不必等待网页重新部署。

- 参数统一单位，同时保存原始单位和值。
- 每条记录保存作者 GitHub 用户名、工艺时间和录入时间。
- 附件按原始字节存储。单文件50 MiB以内，下载校验 SHA-256。
- 相同提交编号重试不会重复建立工艺；同记录同名同内容的附件不会重复。
- 每次写入先读最新分支，创建包含元数据和文件的同一次 Git 提交，再以 force=false 推进分支。
- 若其他成员已提交，重新读取并重试，最多4次。不会强制覆盖他人的记录。分支保护阻止写入时应由维护者处理规则，不由网页绕过。
- 本机 SQLite 与 GitHub 是两个独立存储模式，切换不会自动上传历史数据库或任何实验附件。

## 技术边界

这是面向小团队的 Git 文件存储，不是事务数据库。索引为 JSON，当前上限5 MiB；条目数和附件历史过大时，应迁移专用数据库/文件存储。写入校验在浏览器执行，拥有仓库权限的成员仍可通过 Git 直接修改文件，因此仓库成员必须可信并遵守数据规范。

工艺记录与各附件分别提交，附件失败时在已有工艺的附件区域补传。不要通过删除文件来认为已撤回公开数据：Git 历史会保留旧版本。

## 网页发布

`.github/workflows/pages.yml` 只从静态资源白名单构建并发布 Pages：HTML、CSS、JS、参数目录。不发布 SQLite、令牌、原始测试ZIP或备份目录。`scripts/build_pages.py` 可本地构建到 `dist/pages/`。

GitHub 仓库 Settings → Pages → Source 选择 GitHub Actions。此配置本身不等于发布成功；还需要 main 上包含工作流并且部署任务成功。免费公开仓库可使用 Pages。若以后改私有，需重新确认 Pages 套餐和访问方案。

验证：Python回归测试、Node GitHub API模拟测试（包含并发冲突、丢失响应重试、权限拒绝、附件校验），以及静态发布文件白名单测试。

参考：[GitHub REST跨域访问](https://docs.github.com/en/rest/using-the-rest-api/using-cors-and-jsonp-to-make-cross-origin-requests)、[Git引用非强制更新](https://docs.github.com/en/rest/git/refs)、[个人令牌及限制](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)。
