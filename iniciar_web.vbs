Set WshShell = CreateObject("WScript.Shell")
basePath = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
pythonw = basePath & "runtime\python\pythonw.exe"
script = basePath & "silence_cutter.py"

If CreateObject("Scripting.FileSystemObject").FileExists(pythonw) Then
    WshShell.Run """" & pythonw & """ """ & script & """ --gui", 0, False
Else
    WshShell.Run "pythonw """ & script & """ --gui", 0, False
End If
