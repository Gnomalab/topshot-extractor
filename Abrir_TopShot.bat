@echo off
chcp 65001 >nul
title TopShot v0.9.1

echo.
echo  TopShot v0.9.1 - Smart Frame Extractor
echo  by Gnomalab Studio 2026  -  www.gnomalab.es
echo  =============================================
echo  Comprobando dependencias...
echo.

pip install opencv-python numpy Pillow customtkinter tkinterdnd2 --quiet --exists-action i

echo.
echo  Abriendo TopShot...
echo.

python "%~dp0topshot_extractor.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR al iniciar. Asegurate de tener Python instalado:
    echo  https://www.python.org/downloads/
    pause
)
