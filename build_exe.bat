@echo off
rem Gera o executavel do Uniasselvi App (pasta dist\UniasselviApp\ com UniasselviApp.exe)
rem Aponte PYTHON para o interpretador do seu ambiente; nao ha caminho de maquina aqui.
cd /d "%~dp0"

if "%PYTHON%"=="" set PYTHON=python

"%PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name "UniasselviApp" --icon "assets\app.ico" --add-data "assets;assets" launcher.py
if errorlevel 1 goto :fail

rem dados do app (config/senha/estado) vivem ao lado do .exe
if exist config.json copy /y config.json dist\UniasselviApp\ >nul
if exist .cred copy /y .cred dist\UniasselviApp\.cred >nul
if exist state.json copy /y state.json dist\UniasselviApp\ >nul
echo.
echo OK! Executavel em: %~dp0dist\UniasselviApp\UniasselviApp.exe
goto :end
:fail
echo Falha na geracao do executavel.
:end
