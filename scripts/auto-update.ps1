# opto-hot 本地每 6 小时自动更新脚本（配合 install-schedule.ps1 的计划任务使用）
# 手动运行：powershell -ExecutionPolicy Bypass -File scripts\auto-update.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[auto-update] 开始采集 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
python collector\collect.py --limit 25
if ($LASTEXITCODE -ne 0) { Write-Host "[auto-update] 采集失败，跳过推送"; exit 1 }

# 对外契约自检：产物缺端点或形状不对就不提交（与 CI 同一道关）
python collector\collect.py --check
if ($LASTEXITCODE -ne 0) { Write-Host "[auto-update] 契约自检未通过，跳过提交"; exit 1 }

git add data dist
if (-not (git diff --cached --quiet)) {
  git commit -m "chore: 本地定时刷新光电热点数据 $(Get-Date -Format 'yyyy-MM-ddTHH:mmZ')"
  git push origin master
} else {
  Write-Host "[auto-update] 数据无变化，跳过提交"
}

# 已停止向 CloudBase 同步（2026-08-05）；如需手动部署可运行 scripts\cloudbase-deploy.ps1

Write-Host "[auto-update] 完成 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"