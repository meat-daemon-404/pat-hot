# PAT-HOT 本地定时刷新脚本（配合 install-schedule.ps1 注册的计划任务使用）
# 手动运行：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\auto-update.ps1
# 只跑前置检查、不采集不提交：加 -CheckOnly
#
# 这个脚本会真的 git commit + push，所以先做四道前置检查，任何一道不过就退出、
# 什么都不提交。每一道都对应今天实际踩到或见到的坑：
#   1) 跑错仓库：本机注册的计划任务指向 D:\Project（改名前的 opto-hot 检出），
#      每天往已废弃的 opto-hot.git 推 "本地定时刷新光电热点数据"，而本站数据
#      一次也没被它刷新过。现在先核对 origin 地址。
#   2) 工作树脏：多个会话并行改同一份代码时，`git add data dist` 会把别人未提交
#      的模板/代码改动一起卷进一次自动提交。只允许 data/ 与 dist/ 有改动。
#   3) 落后于远端：本地 master 落后就先拉取，避免把刷新提交到一个旧基线上。
#   4) 没有 SENSENOVA_API_KEY：不带 --llm 的采集会重建全部条目，已发布的
#      zh_full / llm_summary / llm_score / event 字段会整批消失（页面照样 200、
#      契约自检照样绿，内容却静默变薄）。CI 的定时任务带 --llm，本地不带就会把
#      线上增强抹掉，所以默认拒绝，除非显式 -AllowNoKey。
param(
  [switch]$CheckOnly,     # 只跑前置检查
  [switch]$Force,         # 跳过检查 2（脏树）
  [switch]$AllowNoKey,    # 跳过检查 4（无 key 采集，会清掉已发布的 LLM 字段）
  [string]$PythonExe = "python"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Fail([string]$msg) {
  Write-Host "[auto-update] 中止：$msg"
  exit 1
}

# --- 检查 1：确认这是 PAT-HOT 仓库，不是改名前的 opto-hot 检出 ---
$origin = (git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $origin) {
  Fail "当前目录没有可用的 git origin：$Root 不是 PAT-HOT 仓库"
}
if ($origin -notmatch 'pat-hot') {
  Fail ("origin 指向 " + $origin.Trim() + "，不是 pat-hot 仓库。" +
        "旧计划任务若指向改名前的 opto-hot 检出，先注销它：" +
        "Unregister-ScheduledTask -TaskName opto-hot-update -Confirm:`$false")
}
Write-Host "[auto-update] 仓库确认：$($origin.Trim())"

# --- 检查 2：工作树只允许 data/ 与 dist/ 有改动 ---
$foreign = @(git status --porcelain | ForEach-Object { $_.Substring(3) } |
             Where-Object { $_ -notmatch '^(data|dist)/' })
if ($foreign.Count -gt 0 -and -not $Force) {
  Write-Host "[auto-update] 工作树里有 data/dist 之外的改动，拒绝自动提交："
  $foreign | Select-Object -First 20 | ForEach-Object { Write-Host "             $_" }
  Fail "这些改动可能属于别的会话，自动提交会把它们一起打包（确要忽略加 -Force）"
}

# --- 检查 3：本地不应落后于远端 ---
git fetch origin | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "无法联系远端（网络抖动？），本次不提交" }
$behind = [int](git rev-list --count "HEAD..origin/master" 2>$null)
if ($behind -gt 0) { Fail "本地落后远端 $behind 个提交，先 git pull --rebase 再刷新" }

if ($CheckOnly) {
  Write-Host "[auto-update] 前置检查通过（-CheckOnly，未采集未提交）"
  exit 0
}

# --- 检查 4：没有 key 就不要覆盖带 LLM 增强的线上数据 ---
if (-not $env:SENSENOVA_API_KEY -and -not $AllowNoKey) {
  Fail ("未设置 SENSENOVA_API_KEY。不带 --llm 的采集会重建全部条目并丢掉已发布的 " +
        "zh_full/llm_summary/llm_score/event 字段。要么设好 key，要么明确加 -AllowNoKey。")
}

Write-Host "[auto-update] 开始采集 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
$collectArgs = @("collector\collect.py", "--limit", "25")
if ($env:SENSENOVA_API_KEY) { $collectArgs += "--llm" }   # 与 CI 同口径
& $PythonExe @collectArgs
if ($LASTEXITCODE -ne 0) { Fail "采集失败（exit $LASTEXITCODE），不提交" }

# 对外契约自检：与 CI 同一道关，产物坏 / 产物旧于模板就不提交
& $PythonExe collector\collect.py --check
if ($LASTEXITCODE -ne 0) { Fail "契约自检未通过，跳过提交" }

git add data dist
if (git diff --cached --quiet) {
  Write-Host "[auto-update] 数据无变化，跳过提交"
  exit 0
}
git commit -m "chore: 本地刷新 PAT-HOT 数据 $(Get-Date -Format 'yyyy-MM-ddTHH:mmZ')" | Out-Null

# 与远端定时任务撞车时直接 push 会被拒（non-fast-forward）；拉取后重试一次
git push origin master 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[auto-update] push 被拒，拉取远端更新后重试"
  git pull --rebase origin master
  if ($LASTEXITCODE -ne 0) { Fail "rebase 冲突，请人工处理后再 push（提交已在本地，没有丢）" }
  git push origin master
  if ($LASTEXITCODE -ne 0) { Fail "push 仍然失败，稍后手动重试" }
}

# CloudBase 已于 2026-08-05 下线，本站只走 GitHub Pages（CI 自动部署）与
# Cloudflare Pages（按需摘要 Function，需手动 wrangler 发布，见 README）。
Write-Host "[auto-update] 完成 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
