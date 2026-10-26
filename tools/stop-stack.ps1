# Останавливает локальный стек обменника: супервизор, бот, туннель, start.ps1.
# Отдельный файл, чтобы фильтр по командной строке не совпал с самим вызывающим.
#
# Супервизор (autostart.ps1) гасим первым: иначе он поднимет стек заново через
# несколько секунд после остановки бота.
$exclude = @($PID, $PPID)
$targets = Get-CimInstance Win32_Process | Where-Object {
  $_.ProcessId -notin $exclude -and $_.CommandLine -and (
    $_.CommandLine -match 'autostart\.ps1' -or
    $_.CommandLine -match 'start-hidden' -or
    $_.CommandLine -match 'bot\.main' -or
    $_.CommandLine -match 'cloudflared' -or
    $_.CommandLine -match 'tunnelmole' -or
    $_.CommandLine -match 'serve-webapp' -or
    $_.CommandLine -match '\\start\.ps1'
  )
}
foreach ($process in $targets) {
  Write-Output "останавливаю $($process.Name) [$($process.ProcessId)]"
  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Output 'готово'
