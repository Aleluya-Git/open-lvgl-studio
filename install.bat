@echo off
setlocal
cd /d "%~dp0"
echo === Open LVGL Studio - instalacion ===
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
if not exist .venv (
    echo Creando entorno virtual .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo Creando acceso directo "Open LVGL Studio" con su icono ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%~dp0Open LVGL Studio.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0main.py\"'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0olvgl\resources\app_icon.ico'; $s.Save()" >nul 2>nul
echo.
echo Instalacion completada. Ejecuta run.bat para abrir la aplicacion
echo o autoprueba.bat para comprobar que todo funciona.
pause
exit /b 0
:error
echo.
echo ERROR durante la instalacion. Revisa los mensajes anteriores.
pause
exit /b 1
