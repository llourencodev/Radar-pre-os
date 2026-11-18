@echo off
chcp 65001 >nul
title Radar de Precos
set "APP=%~dp0"
cd /d "%APP%"
set "VPY=%APP%.venv\Scripts\python.exe"

rem Se o radar ja estiver rodando, so abre o navegador
netstat -ano | findstr /r /c:":8010 .*LISTENING" >nul && (
  echo O Radar de Precos ja esta rodando. Abrindo o navegador...
  start "" http://localhost:8010
  timeout /t 3 >nul
  exit /b 0
)

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

if not exist "%VPY%" (
  echo Preparando o ambiente pela primeira vez. Isso leva cerca de 1 minuto...
  %PY% -m venv "%APP%.venv" || (echo. & echo Python nao encontrado. Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH". & pause & exit /b 1)
  "%VPY%" -m pip install --upgrade pip >nul
  "%VPY%" -m pip install -r "%APP%requirements.txt" || (echo. & echo Falha ao instalar dependencias. Verifique a internet e tente novamente. & pause & exit /b 1)
)

if not exist "%APP%.env" copy "%APP%.env.example" "%APP%.env" >nul

rem Console em UTF-8 para o Python nao fechar ao escrever acentos
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

"%VPY%" "%APP%run.py" %*
echo.
echo O servidor foi encerrado. Se apareceu um erro acima, copie a mensagem.
pause