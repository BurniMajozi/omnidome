@echo off
rem omnidome - agent orchestrator CLI (services\agent_orchestrator\cli.py).
rem Usage: scripts\omnidome --help   (add scripts\ to PATH to call it as `omnidome`)
setlocal
set "REPO=%~dp0.."
set "PY=%REPO%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONPATH=%REPO%;%PYTHONPATH%"
set "PYTHONIOENCODING=utf-8"
"%PY%" -m services.agent_orchestrator.cli %*
