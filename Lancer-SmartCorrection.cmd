@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  set "SC_PYTHON=python"
) else (
  set "SC_PYTHON=py -3"
)
%SC_PYTHON% -X utf8 -c "import pypdf" >nul 2>nul
if errorlevel 1 (
  echo Installation des dependances de l'interface...
  %SC_PYTHON% -X utf8 -m pip install ".[gui]"
  if errorlevel 1 goto failed
)
%SC_PYTHON% -X utf8 -m moteur gui
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Le lancement a echoue. Consulter le message ci-dessus et le README.
pause
exit /b 1
