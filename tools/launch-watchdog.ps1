# Запускает супервизор (autostart.ps1) ОТДЕЛЬНО от дерева процессов DSH.
#
# Зачем через WMI: процессы, созданные обычным Start-Process, попадают в job-объект
# агента и умирают вместе с ним. Win32_Process.Create создаёт процесс через службу
# WMI (WmiPrvSE), поэтому супервизор продолжает работать, даже когда DSH закрыт.
$ErrorActionPreference = 'Stop'
$target = (Resolve-Path (Join-Path $PSScriptRoot '..\autostart.ps1')).Path
$commandLine = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $target + '"'
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $commandLine }
if ($result.ReturnValue -ne 0) {
  throw "WMI не смог запустить супервизор (ReturnValue=$($result.ReturnValue))"
}
Write-Output "супервизор запущен, PID=$($result.ProcessId)"
Write-Output "лог: .run\autostart.log, адрес: .run\public-url.txt"
