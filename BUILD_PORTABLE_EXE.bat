@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul || (echo Install 64-bit Python 3.12 for Windows first.& pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto :error
set "PYTHON=.venv\Scripts\python.exe"
"%PYTHON%" -m pip install --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto :error
"%PYTHON%" -m unittest discover -s tests -v
if errorlevel 1 goto :error
"%PYTHON%" scripts\smoke_test.py
if errorlevel 1 goto :error
"%PYTHON%" scripts\build_windows.py
if errorlevel 1 goto :error
"%PYTHON%" scripts\smoke_test.py --exe "dist\Dynasty Warriors Strikeforce PS3 Save Editor.exe"
if errorlevel 1 goto :error
echo.
echo Built and checked: dist\Dynasty Warriors Strikeforce PS3 Save Editor.exe
pause
exit /b 0
:error
echo.
echo Build or verification failed. No release should be published from this build.
pause
exit /b 1
