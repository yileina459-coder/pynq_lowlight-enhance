# 代码包：整理结果与 RAR 转换

## 1. 已生成的包

| 项 | 值 |
|---|---|
| 暂存目录 | `dist\低延迟视觉增强终端_源码包\`（可先解压检查） |
| 压缩包 | `dist\低延迟视觉增强终端_源码包.zip` |
| 文件数 | 448 |
| 原始大小 | 60.8 MB |
| 压缩后 | 26.5 MB（表单上限 200 M，余量充足） |

打包口径 = **git 已跟踪的全部文件** + `docs/final_submission_plan.md` + `README_提交说明.md`。
因此 `.gitignore` 里排除的中间产物自动不会进来。

### 包含

- `board/`（47.6 MB）：5 套 overlay 的 `.bit`/`.hwh`/`.xsa`、板端 Python、测量 CSV、证据截图
- `build/`（5.0 MB）：Vivado/HLS 构建脚本与综合、实现报告（不含 `proj/`、`*.runs/`、`export/`）
- `src/`、`sim/`：HLS 算子源码与测试台
- `tools/`、`data/`、`skill/`：主机端工具、测试图、诊断 Skill
- `docs/`、`report/`：事实表、复现步骤、设计报告、海报、汇报幻灯片

### 排除

- `.git/`（53 MB 历史）、`.tmp/`（438 MB 草稿）、`build/` 下 1.8 GB 中间产物
- `dist/` 自身（避免包中套包）

## 2. 转成 RAR（表单要求 .rar）

本机没有 WinRAR（`winget` 源里也没有该包，已确认失败），7-Zip 只能写 zip、不能写 rar。两条路：

**A. 装 WinRAR 后一键转**

1. 到 <https://www.rarlab.com/download.htm> 下载 `winrar-x64-*.exe`（试用期 40 天，足够打包）。
2. 默认路径安装后，双击 `dist\make_rar.ps1`（或右键“使用 PowerShell 运行”）。
3. 产物 `dist\低延迟视觉增强终端_源码包.rar`，约 25 MB。

脚本做的事等价于：

```powershell
& "C:\Program Files\WinRAR\Rar.exe" a -r -m5 "dist\低延迟视觉增强终端_源码包.rar" "dist\低延迟视觉增强终端_源码包"
```

**B. 先试 zip**

有的平台文案写 RAR、实际接受 zip。上传页若能选到 zip 并成功提交，就用 zip；被拦下再走 A。

## 3. 上传前自检

1. 解压到空目录，确认 `README_提交说明.md` 在根目录。
2. `python tools\check_consistency.py --strict` → 应输出 `CONSISTENCY PASS`。
3. 抽查 `board\hdmi_stream_enhance\enhance_hdmi.bit` 能打开、大小 3.9 MB 左右。
4. 确认包内**没有** `.tmp`、`xlicdiag.rpt`、个人路径日志。

## 4. 重新打包

```powershell
python .tmp\stage_pkg.py     # 重新暂存
python .tmp\make_zip.py      # 重新压缩
```
