@echo off
setlocal
cd /d "%~dp0"
echo === Open LVGL Studio - extension de VS Code ===
if not exist .venv\Scripts\python.exe (
    echo Primero ejecuta install.bat
    pause
    exit /b 1
)
set VSIX=
for /f "delims=" %%i in ('.venv\Scripts\python.exe tools\build_vsix.py') do set VSIX=%%i
if not defined VSIX goto :error
rem La extension encuentra la aplicacion gracias a este fichero
if not exist "%USERPROFILE%\.olvgl" mkdir "%USERPROFILE%\.olvgl"
> "%USERPROFILE%\.olvgl\studio_path.txt" echo %~dp0
where code >nul 2>nul
if errorlevel 1 goto :manual
call code --install-extension "%VSIX%" --force
if errorlevel 1 goto :manual
echo.
echo Extension instalada. Reinicia VS Code (o "Developer: Reload Window").
echo Abre un YAML con lvgl: y pulsa Ctrl+K V para la vista previa o Ctrl+Alt+D para el disenador.
pause
exit /b 0
:manual
echo.
echo No se encontro el comando "code" de VS Code.
echo Instala la extension a mano: VS Code ^> Extensiones ^> ... ^> Instalar desde VSIX... y elige:
echo   %VSIX%
pause
exit /b 0
:error
echo.
echo ERROR al empaquetar la extension.
pause
exit /b 1
