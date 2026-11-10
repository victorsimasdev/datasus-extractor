@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Parar e exportar a coleta DATASUS
echo ============================================================
echo  PARAR A COLETA NESTE COMPUTADOR E COPIAR TUDO
echo ============================================================
echo.
python migrar.py exportar
echo.
pause
