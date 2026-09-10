Set s=CreateObject("WScript.Shell")
base=CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
s.Run "pythonw.exe """ & base & "\Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw"""", 0, False
