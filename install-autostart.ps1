# Регистрирует задачу в Планировщике Windows: автозапуск обменника при входе в систему.
# Запуск (один раз): правый клик -> "Выполнить с помощью PowerShell"
# Удалить автозапуск: Unregister-ScheduledTask -TaskName 'Fastobmennik' -Confirm:$false
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$taskName = 'Fastobmennik'
$script = Join-Path $PSScriptRoot 'autostart.ps1'
$workdir = $PSScriptRoot

if (-not (Test-Path $script)) { throw "не найден $script" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
  -WorkingDirectory $workdir

$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = 'PT30S'

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName
Write-Host "✓ задача «$taskName» зарегистрирована"
Write-Host "  запуск: при входе в Windows (через 30 секунд)"
Write-Host "  скрипт: $script"
Write-Host "  логи:   .run\autostart.log и .run\start.log"
Write-Host ''
Write-Host "Проверить сейчас: Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Выключить автозапуск: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
