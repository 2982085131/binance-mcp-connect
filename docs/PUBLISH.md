# 把项目上传到 GitHub（新手版）

本仓库已经初始化好 git，并且完成了首个提交。你只需要在 GitHub 上建一个空仓库，
然后把本地提交推上去。

> 当前分支：`main`（如果你看到 `master`，先执行 `git branch -M main`）
> 当前没有配置远程仓库（`git remote -v` 为空）。

---

## 方式 A：网页 + HTTPS + Personal Access Token（推荐）

### 1. 在 GitHub 建空仓库

1. 登录 GitHub，点右上角 `+` → **New repository**；
2. Repository name 填 `binance-mcp-connect`；
3. 选择 **Public**（开源）或 **Private**（私有，自己决定）；
4. **不要**勾选 "Add a README file"、"Add .gitignore"、"Choose a license"
   （本仓库已经有了，勾选会导致推送冲突）；
5. 点 **Create repository**，复制页面上的仓库地址，例如：
   `https://github.com/<你的用户名>/binance-mcp-connect.git`

### 2. 生成本地推送用的 Token

GitHub 从 2021 年起不再接受账号密码推送，必须用 **Personal Access Token**：

1. 右上角头像 → **Settings**；
2. 左侧最下方 → **Developer settings**；
3. **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**；
4. Note 随便写（如 `push-binance-mcp`），Expiration 选 30 天；
5. 勾选权限：
   - **`repo`**（推送代码必需）
   - **`workflow`**（本仓库有 `.github/workflows/ci.yml`，不勾会推送失败）
6. 点 **Generate token**，**立刻复制**（页面关掉就再也看不到）。

### 3. 在本地推送

打开 PowerShell：

```powershell
cd D:\agentWork\youziWater\binance-mcp-connect
git branch -M main
git remote add origin https://github.com/<你的用户名>/binance-mcp-connect.git
git push -u origin main
```

推送时会弹窗或提示输入：

- **Username**：你的 GitHub 用户名
- **Password**：粘贴刚才的 **Token**（不是账号密码）

看到 `branch 'main' set up to track 'origin/main'` 就成功了。

### 4. 验证

打开 `https://github.com/<你的用户名>/binance-mcp-connect`：

- README 应该正常渲染；
- 顶部 **Actions** 标签会出现 CI 运行（Ubuntu/Windows × Python 3.10/3.12）；
- 仓库里**不应该**出现 `token.json`、`*.age`、`.env`（`.gitignore` 已排除）。

---

## 方式 B：GitHub Desktop（最省事，适合不想碰命令行）

1. 下载安装 [GitHub Desktop](https://desktop.github.com/)；
2. 登录 GitHub 账号；
3. 菜单 **File → Add local repository**，选
   `D:\agentWork\youziWater\binance-mcp-connect`；
4. 右上角点 **Publish repository**；
5. 取消勾选 "Keep this code private" 就是公开仓库，点 **Publish**。

不需要手动配 Token，Desktop 会处理登录。

---

## 方式 C：GitHub CLI（`gh`）

```powershell
winget install GitHub.cli
gh auth login          # 按提示选 GitHub.com → HTTPS → 浏览器登录
cd D:\agentWork\youziWater\binance-mcp-connect
gh repo create binance-mcp-connect --public --source=. --remote=origin --push
```

一条命令完成建仓 + 推送。

---

## 常见错误

| 报错 | 原因 | 解决 |
|---|---|---|
| `Support for password authentication was removed` | 用了账号密码 | 改用 PAT |
| `refusing to allow a Personal Access Token to create or update workflow` | PAT 没勾 `workflow` | 重新生成，勾上 `workflow` |
| `remote origin already exists` | 重复添加远程 | `git remote set-url origin <新地址>` |
| `failed to push some refs` / `fetch first` | GitHub 仓库里已有 README | `git pull --rebase origin main` 再 `git push`，或删掉远程仓库重建空仓库 |
| `403 Permission denied` | PAT 过期或权限不足 | 重新生成 PAT |
| `fatal: not a git repository` | 不在项目目录 | `cd` 到 `binance-mcp-connect` |

---

## 推送前的安全检查（重要）

```powershell
cd D:\agentWork\youziWater\binance-mcp-connect
git status --short
git ls-files | Select-String -Pattern 'token|secret|\.env|\.age'
```

- `git status` 里如果有 `token.json`、`*.age`、`.env`，先删掉或确认已在 `.gitignore`；
- 本仓库已用 `scan_secrets.py` 扫描过，**没有**提交任何密钥；
- 不要把 `D:\agentWork\youziWater\币安API.txt` 或
  `quant_research\03_results\mcp\token.json` 复制进仓库。

---

## 之后更新代码

```powershell
cd D:\agentWork\youziWater\binance-mcp-connect
git add .
git commit -m "describe your change"
git push
```

---

## English summary

1. Create an **empty** repo on GitHub (no README/license/gitignore).
2. Create a **classic PAT** with `repo` and `workflow` scopes.
3. Run:
   ```bash
   cd binance-mcp-connect
   git branch -M main
   git remote add origin https://github.com/<you>/binance-mcp-connect.git
   git push -u origin main
   ```
   Use your GitHub username and the **token** as the password.
4. Alternatively use GitHub Desktop (Publish repository) or `gh repo create`.
5. Never commit `token.json`, `*.age` or `.env`; `.gitignore` already excludes them.
