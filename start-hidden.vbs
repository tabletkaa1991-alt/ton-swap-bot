' Скрытый запуск обменника после входа в Windows (без окна консоли).
' Кладётся в папку «Автозагрузка»: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
Dim shell, fso, scriptDir, target
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\autostart.ps1"

If Not fso.FileExists(target) Then
  WScript.Quit 1
End If

shell.CurrentDirectory = scriptDir
shell.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & target & """", 0, False
