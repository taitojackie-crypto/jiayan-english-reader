Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

WshShell.Run ".venv\Scripts\pythonw app.py", 0, False

WScript.Sleep 3000
WshShell.Run "http://127.0.0.1:5000", 1, False

Set WshShell = Nothing
