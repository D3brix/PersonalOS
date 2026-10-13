@echo off
rem Double-click to install PersonalOS for the current user (no administrator rights needed).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
