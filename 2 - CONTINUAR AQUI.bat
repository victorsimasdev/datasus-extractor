@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Continuar a coleta DATASUS neste computador
echo ============================================================
echo  CONTINUAR A COLETA NESTE COMPUTADOR
echo ============================================================
echo.

rem --- 1. Python (instala o 3.12 se nao houver) ---
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo [1/4] Python nao encontrado. Instalando o Python 3.12...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
)
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo ERRO: nao consegui instalar o Python automaticamente.
  echo Instale pelo site python.org ^(marque "Add python.exe to PATH"^) e rode este arquivo de novo.
  pause & exit /b 1
)
echo [1/4] Python OK

rem --- 2. Google Chrome (a coleta usa o Chrome instalado) ---
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if not defined CHROME (
  echo [2/4] Google Chrome nao encontrado. Instalando...
  winget install -e --id Google.Chrome --accept-package-agreements --accept-source-agreements
)
echo [2/4] Chrome OK

rem --- 3. Bibliotecas ---
echo [3/4] Instalando/conferindo as bibliotecas...
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo ERRO ao instalar as bibliotecas. Confira a internet e rode de novo.
  pause & exit /b 1
)
echo [3/4] Bibliotecas OK

rem --- 4. Confere os dados e retoma a coleta ---
echo [4/4] Conferindo os dados copiados e retomando a coleta...
%PY% migrar.py continuar
echo.
echo Pode fechar esta janela: a coleta continua rodando em segundo plano.
pause
