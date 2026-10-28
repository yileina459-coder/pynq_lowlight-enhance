# 上传到 GitHub

表单第 7 项要的是 **GitHub 链接**（≤200 字符）。当前仓库只有 Gitee 远端
（`origin` → `https://gitee.com/kylnnn/year-26--fpga-amd-track.git`），分支 `master`，446 个跟踪文件，
最大单文件 4.4 MB（GitHub 上限 100 MB/文件，无压力）。下面是把它镜像到 GitHub 的完整步骤。

## 0. 先把要交的东西提交

```powershell
cd C:\Users\79171\Desktop\FPGA
git status                 # 当前：M report/submission_text.md；?? docs/final_submission_plan.md；?? report/assets/
# 代码包是产物，别提交
Add-Content .gitignore "`ndist/"
git add -A
git commit -m "docs: final submission plan, report figures, package script"
```

## 1. 建仓库

网页 <https://github.com/new>：

- Repository name：`pynq-lowlight-enhance`（随意，好记即可）
- 可见性：**Public**（评委要能打开；Private 需要给邀请，不建议）
- **不要**勾 "Add a README file / .gitignore / license"（本地已有，勾了会冲突）

## 2. 加远端并推送

```powershell
git remote add github https://github.com/<你的用户名>/pynq-lowlight-enhance.git
git push -u github master:main
```

- `master:main` = 把本地 `master` 推成 GitHub 的 `main` 分支（GitHub 默认分支叫 main，看着更顺）。
  想保留 `master` 名字就写 `git push -u github master`，然后在网页 Settings → Branches 改默认分支。
- 首次会让你认证，见下一节。

## 3. 认证（本机有个已知坑）

之前测过：`git ls-remote` 报
`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS 0x8009030e`。
说明本机 git 的 Windows 凭据通道有问题，按顺序试：

**方案 A：PAT（最快）**

1. <https://github.com/settings/tokens> → Generate new token (classic) → 勾 `repo` → 生成。
2. 推送时用户名填 GitHub 用户名，**密码处粘贴 PAT**。
3. 记住凭据：`git config --global credential.helper manager`（弹窗登录一次即可）。

**方案 B：换 TLS 后端**

```powershell
git config --global http.sslBackend openssl
git push -u github master:main
```

**方案 C：SSH（最稳，不受凭据通道影响）**

```powershell
ssh-keygen -t ed25519 -C "you@example.com" -f $env:USERPROFILE\.ssh\id_ed25519
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard
# 粘贴到 https://github.com/settings/keys → New SSH key
git remote set-url github git@github.com:<你的用户名>/pynq-lowlight-enhance.git
ssh -T git@github.com      # 出现 "Hi <user>!" 即通
git push -u github master:main
```

## 4. 验证

1. 开一个**隐身窗口**打开仓库首页，确认不用登录也能看到代码（Public 生效）。
2. README 的图能正常显示（`report/` 里的相对路径图）。
3. 抽查 `board/hdmi_stream_enhance/` 里 `.bit` 文件存在（GitHub 会把 >1 MB 的文件标为 "binary"）。
4. 全文搜一遍 `教师`、`学校`、本机绝对路径（`C:\Users\79171`）——仓库里出现本机路径不算错，但若含真实姓名/学号要清掉。

## 5. 填表单

第 7 项直接填仓库地址：

```
https://github.com/<你的用户名>/pynq-lowlight-enhance
```

- 不要带 `.git` 后缀，不要带分支路径。
- 长度约 50 字符，远小于 200。

## 6. 备注

- **别把 `dist\*.zip`（26 MB）提交进 git**：会让仓库每次 clone 都拖这个包，上一步已加进 `.gitignore`。
- Gitee 与 GitHub 可以并存，`origin` 仍是 Gitee，`github` 是镜像；以后同步：
  `git push origin master && git push github master:main`。
- 如果只想公开“成果快照”而不想公开调试历史，可在推完后新建一个干净分支再设为默认：
  `git checkout --orphan release && git commit -m "release" && git push -u github release:main`。
