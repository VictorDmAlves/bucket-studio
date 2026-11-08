@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 local_server.py
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        python local_server.py
    ) else (
        echo Python 3 is required for the optional Ollama bridge.
        echo index.html still works directly for bucketing, cropping and export.
        pause
    )
)
