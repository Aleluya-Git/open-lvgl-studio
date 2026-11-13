@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Primero ejecuta install.bat
    pause
    exit /b 1
)
.venv\Scripts\python.exe autoprueba.py %*
echo.
echo Resultado guardado en autoprueba_resultado.txt y capturas en la carpeta capturas\
pause
