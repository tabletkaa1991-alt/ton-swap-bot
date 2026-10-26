# Убивает все ранее запущенные обёртки/супервизоры и стек обменника.
# Отдельный файл: своя командная строка не содержит искомых слов, поэтому
# фильтр не совпадает с самим скриптом и с вызывающей оболочкой.
$exclude = @($PID, $PPID)

$wrappers = Get-CimInstance Win32_Process | Where-Object {
  $_.ProcessId -notin $exclude -and $_.Name -eq 'powershell.exe' -and
  $_.CommandLine -match '-File.*autostart\.ps1'
}

$stack = Get-CimInstance Win32_Process | Where-Object {
  $_.ProcessId -notin $exclude -and $_.CommandLine -and (
    $_.CommandLine -match 'bot\.main' -or
    $_.CommandLine -match 'serve-webapp' -or
    $_.CommandLine -match 'tunnelmole' -or
    $_.CommandLine -match '\\start\.ps1'
  )
}

foreach ($process in @($wrappers) + @($stack)) {
  Write-Output "kill $($process.Name) [$($process.ProcessId)]"
  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 3
$left = Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and ($_.CommandLine -match 'bot\.main' -or $_.CommandLine -match 'serve-webapp' -or $_.CommandLine -match 'tunnelmole')
}
if ($left) { Write-Output "осталось: $($left.ProcessId -join ',')" } else { Write-Output 'стек остановлен' }
