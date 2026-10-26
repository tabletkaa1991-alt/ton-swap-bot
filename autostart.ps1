# Супервизор локального режима: запускает бота и следит за туннелем.
# Если публичный адрес перестал отвечать (cloudflared отвалился) — перезапускает всё,
# получает новый адрес, обновляет .env и кнопку меню в боте.
# Запускается из автозагрузки: start-hidden.vbs -> этот скрипт.
#
# ЭТО ЛОКАЛЬНЫЙ РЕЖИМ. После переезда на сервер (см. DEPLOY-FREE.md) автозагрузку
# нужно отключить: удалить ярлык start-hidden.vbs из папки «Автозагрузка».
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force .run | Out-Null

function Write-Log([string]$message) {
  "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $message" | Out-File '.run\autostart.log' -Append -Encoding utf8
}

function Stop-Stack {
  # Свой PID и родителя не трогаем: командная строка этого скрипта тоже содержит
  # искомые слова, иначе супервизор убил бы сам себя.
  $exclude = @($PID, $PPID)
  $targets = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -notin $exclude -and $_.CommandLine -and (
      $_.CommandLine -match 'bot\.main' -or
      $_.CommandLine -match 'cloudflared' -or
      $_.CommandLine -match 'tunnelmole' -or
      $_.CommandLine -match 'serve-webapp' -or
      $_.CommandLine -match '\\start\.ps1'
    )
  }
  foreach ($process in $targets) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

function Get-PublicUrl {
  try {
    $value = (Get-Content '.run\public-url.txt' -Raw -ErrorAction Stop).Trim()
    if ($value) { return $value }
  } catch { }
  return $null
}

function Test-Health([string]$url) {
  if (-not $url) { return $false }
  try {
    $response = Invoke-WebRequest "$url/api/health" -UseBasicParsing -TimeoutSec 15
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

Write-Log '=== супервизор запущен ==='

while ($true) {
  try {
    Write-Log 'перезапуск стека'
    Stop-Stack
    Start-Sleep -Seconds 5
    Remove-Item '.run\public-url.txt' -ErrorAction SilentlyContinue

    Start-Process -FilePath 'powershell.exe' `
      -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'start.ps1') `
      -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null

    $url = $null
    for ($i = 0; $i -lt 60; $i++) {
      Start-Sleep -Seconds 2
      $candidate = Get-PublicUrl
      if ($candidate -and (Test-Health $candidate)) { $url = $candidate; break }
    }

    if (-not $url) {
      Write-Log 'стек не поднялся за 2 минуты — повтор через 30 секунд'
      Start-Sleep -Seconds 30
      continue
    }
    Write-Log "стек работает: $url"

    $failures = 0
    while ($true) {
      Start-Sleep -Seconds 45
      if (Test-Health $url) {
        $failures = 0
      } else {
        $failures++
        Write-Log "health не отвечает ($failures/3)"
        if ($failures -ge 3) {
          Write-Log 'туннель умер — перезапуск стека'
          break
        }
      }
    }
  } catch {
    Write-Log "ошибка супервизора: $($_.Exception.Message)"
    Start-Sleep -Seconds 30
  }
}
