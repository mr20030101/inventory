@echo off
rem Build SAIMS for Windows: dist\SAIMS\SAIMS.exe and, if Inno Setup 6 is installed,
rem dist\SAIMS-<version>-Setup.exe
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe ( py -3 -m venv .venv || python -m venv .venv )
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements-dev.txt || exit /b 1
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python -m pytest -q || exit /b 1
set QT_QPA_PLATFORM=
.venv\Scripts\pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\saims.spec || exit /b 1

set ISCC=
where iscc >nul 2>nul && set ISCC=iscc
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC (
    %ISCC% packaging\installer.iss || exit /b 1
    echo Installer written to dist\
) else (
    echo Inno Setup 6 not found: skipped the installer. The app is in dist\SAIMS\
)
