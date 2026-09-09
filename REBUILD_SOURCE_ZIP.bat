@echo off
setlocal
set "BASE=release\Dynasty_Warriors_Strikeforce_PS3_Save_Editor_Source.zip"
set "B64=%TEMP%\DWSF_Source_part3.b64"
set "P3=%TEMP%\DWSF_Source_part3.bin"

copy /b "%BASE%.part3.b64.01"+"%BASE%.part3.b64.02"+"%BASE%.part3.b64.03"+"%BASE%.part3.b64.04" "%B64%" >nul
if errorlevel 1 goto :error

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%B64%'); [IO.File]::WriteAllBytes('%P3%',[Convert]::FromBase64String($s))"
if errorlevel 1 goto :error

copy /b "%BASE%.part1"+"%BASE%.part2"+"%P3%" "Dynasty_Warriors_Strikeforce_PS3_Save_Editor_Source.zip" >nul
if errorlevel 1 goto :error

del "%B64%" 2>nul
del "%P3%" 2>nul
echo.
echo Created successfully:
echo Dynasty_Warriors_Strikeforce_PS3_Save_Editor_Source.zip
echo.
pause
exit /b 0

:error
echo.
echo ERROR: Could not rebuild the source ZIP.
echo.
pause
exit /b 1
