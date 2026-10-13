# 注册 Windows 计划任务：每天 12:00 自动运行 scripts\auto-update.ps1
#
# 改动说明（2026-10-13）：
# - 原来的 [int]$IntervalHours 参数在函数体里从头到尾没被用到，触发器实际是
#   -Daily -At "12:00"。参数留着只会让人以为任务是每 6 小时跑一次（auto-update.ps1
#   的旧注释也正是这么写的）。删掉它，改成能真正决定行为的 -At。
# - 任务名默认值从 opto-hot-update 改为 pat-hot-update（仓库已改名）。
# - 注册前先查有没有指向别的目录的同名/旧名任务并告警：本机实测发现
#   \opto-hot-update 一直在跑 D:\Project（改名前的 opto-hot 检出），每天往
#   已废弃的 opto-hot.git 推数据，而本站数据一次也没被它刷新过。
param(
  [string]$TaskName = "pat-hot-update",
  [string]$At = "12:00"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $Root "scripts\auto-update.ps1"
if (-not (Test-Path $script)) {
  Write-Host "[install-schedule] 找不到 $script，请在仓库根目录下运行"
  exit 1
}

# 旧名任务是否还在、且指向别处？
$legacy = "opto-hot-update"
if ($TaskName -ne $legacy) {
  $old = Get-ScheduledTask -TaskName $legacy -ErrorAction SilentlyContinue
  if ($old) {
    $oldPath = ($old.Actions | Select-Object -First 1).Arguments
    if ($oldPath -notmatch [regex]::Escape($Root)) {
      Write-Host "[install-schedule] 警告：已存在计划任务 \${legacy}，指向别处："
      Write-Host "                   $oldPath"
      Write-Host "                 它每天仍会向那个（多半是改名前的 opto-hot）仓库推送数据。"
      Write-Host "                 要停掉：Unregister-ScheduledTask -TaskName $legacy -Confirm:`$false"
    }
  }
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
  -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Principal $principal -Force | Out-Null

Write-Host "已注册计划任务 $TaskName（每天 $At 运行 $script，含 git push，触发 GitHub Pages 重新部署）"
Write-Host "删除：Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host "提示：脚本要求工作树除 data/ 与 dist/ 外干净，且需要 SENSENOVA_API_KEY"
Write-Host "      才会带 --llm 采集；否则会在前置检查处退出，不动仓库。"
