# Запуск обменника одной командой (локальный режим): бот -> туннель -> .env -> бот.
# Использование: правый клик -> "Выполнить с помощью PowerShell", или в консоли: .\start.ps1
# Остановить: Ctrl+C в этом окне (или .\tools\stop-stack.ps1).
#
# Что изменилось против старой версии: статику и /api отдаёт сам бот (bot/web.py),
# поэтому node-сервер больше не нужен. Порядок такой:
#   1) бот поднимается и занимает 8080 (туннели проверяют, что порт слушается);
#   2) поднимается туннель (tunnelmole, при неудаче — cloudflared);
#   3) полученный https-адрес пишется в .env, бот перезапускается и ставит кнопку.
# Прежняя ошибка «No matching tunnelmole domain» означала, что бесплатный адрес
# tunnelmole перестал существовать: скрипт просто получает новый.
#
# ВАЖНО: локальный режим — временный. Для работы 24/7 без ноутбука нужен сервер,
# см. DEPLOY-FREE.md.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force .run | Out-Null

$python = 'C:\Users\SPBNB\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path $python)) {
  throw "не найден python по пути $python — поправьте переменную python в start.ps1"
}

function Set-WebappUrl([string]$value) {
  $content = [IO.File]::ReadAllText((Join-Path $PWD '.env'))
  $line = "WEBAPP_URL=$value"
  if ($content -match '(?m)^WEBAPP_URL=') {
    $content = $content -replace '(?m)^WEBAPP_URL=.*$', $line
  } else {
    $content = $content.TrimEnd() + "`r`n$line`r`n"
  }
  # Без BOM: с ним первый ключ .env читается не всеми парсерами.
  [IO.File]::WriteAllText((Join-Path $PWD '.env'), $content, (New-Object Text.UTF8Encoding($false)))
}

function Test-LocalHealth {
  try {
    $response = Invoke-WebRequest 'http://127.0.0.1:8080/api/health' -UseBasicParsing -TimeoutSec 3
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Wait-LocalHealth([int]$seconds) {
  for ($i = 0; $i -lt $seconds; $i++) {
    Start-Sleep -Seconds 1
    if (Test-LocalHealth) { return $true }
  }
  return $false
}

function Wait-TunnelUrl([string]$pattern, [int]$tries) {
  for ($i = 0; $i -lt $tries; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path '.run\tunnel.log') {
      $match = Select-String -Path '.run\tunnel.log' -Pattern $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($match) { return $match.Matches[0].Value }
    }
  }
  return $null
}

# Telegram в РФ периодически режут: предупреждаем сразу, а не после десяти
# ошибок в логе. Прокси задаётся в .env (PROXY_URL), VPN тоже подойдёт.
$proxy = ''
$envLine = Select-String -Path '.env' -Pattern '^PROXY_URL=(.+)$' -ErrorAction SilentlyContinue | Select-Object -Last 1
if ($envLine) { $proxy = $envLine.Matches.Groups[1].Value.Trim() }
if (-not $proxy) {
  $reachable = Test-NetConnection api.telegram.org -Port 443 -WarningAction SilentlyContinue -InformationLevel Quiet
  if (-not $reachable) {
    Write-Host '! api.telegram.org не отвечает: включите VPN или впишите PROXY_URL в .env, иначе бот не получит сообщения.' -ForegroundColor Yellow
  }
}

$env:PYTHONPATH = 'vendor'
$env:PYTHONIOENCODING = 'utf-8'
$env:HOST = '127.0.0.1'

Write-Host '1/3 черновой запуск бота (занять 8080)...'
Set-WebappUrl ''
$boot = Start-Process -FilePath $python -ArgumentList '-m','bot.main' `
  -WorkingDirectory $PWD -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput '.run\bot-boot.out' -RedirectStandardError '.run\bot-boot.err'
if (-not (Wait-LocalHealth 40)) {
  if ($boot -and -not $boot.HasExited) { Stop-Process -Id $boot.Id -Force -ErrorAction SilentlyContinue }
  Write-Host '✗ бот не поднялся на 8080. Хвост .run\bot-boot.err:' -ForegroundColor Red
  Get-Content '.run\bot-boot.err' -Tail 20 -ErrorAction SilentlyContinue
  throw 'бот не запустился — исправьте ошибку выше'
}
Write-Host '   бот слушает 8080'

Write-Host '2/3 туннель...'
Remove-Item '.run\tunnel.log' -ErrorAction SilentlyContinue
$url = $null

# Вариант 1: tunnelmole (уже стоит в npm-кеше, работает из РФ без VPN).
Start-Process -FilePath 'cmd.exe' `
  -ArgumentList '/c','npm exec --yes --cache ..\.npm-cache -- tunnelmole 8080 > .run\tunnel.log 2>&1' `
  -WorkingDirectory $PWD -WindowStyle Hidden | Out-Null
$url = Wait-TunnelUrl 'https://[a-z0-9\-]+\.tunnelmole\.net' 180

# Вариант 2: cloudflared (стабильнее там, где Cloudflare не блокируют).
if (-not $url) {
  Write-Host '   tunnelmole не ответил, пробую cloudflared...'
  $cloudflared = Join-Path $PWD 'tools\bin\cloudflared.exe'
  if (Test-Path $cloudflared) {
    Remove-Item '.run\tunnel.log' -ErrorAction SilentlyContinue
    Start-Process -FilePath $cloudflared `
      -ArgumentList 'tunnel','--url','http://127.0.0.1:8080','--protocol','http2','--no-autoupdate','--logfile','.run\tunnel.log' `
      -WorkingDirectory $PWD -WindowStyle Hidden | Out-Null
    $url = Wait-TunnelUrl 'https://[a-z0-9\-]+\.trycloudflare\.com' 180
  }
}

if ($url) {
  Write-Host "   адрес: $url"
  [IO.File]::WriteAllText((Join-Path $PWD '.run\public-url.txt'), $url, (New-Object Text.UTF8Encoding($false)))
} else {
  Write-Host '   ! туннель не поднялся: команды бота будут работать, кнопка WebApp — нет.' -ForegroundColor Yellow
  Write-Host '   ! для 24/7 нужен сервер — DEPLOY-FREE.md.' -ForegroundColor Yellow
  Remove-Item '.run\public-url.txt' -ErrorAction SilentlyContinue
}

Write-Host '3/3 перезапуск бота с адресом (Ctrl+C — остановить)...'
if ($boot -and -not $boot.HasExited) {
  Stop-Process -Id $boot.Id -Force -ErrorAction SilentlyContinue
  # Дать порту освободиться, иначе второй экземпляр упадёт с «address already in use».
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 250
    if (-not (Test-LocalHealth)) { break }
  }
}
Set-WebappUrl $(if ($url) { "$url/" } else { '' })
& $python -m bot.main
