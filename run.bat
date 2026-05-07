@echo off
REM One-shot runner for Windows Task Scheduler.
REM Runs tracker.py inside WSL so it uses the same Python environment
REM you tested with.

wsl.exe -e bash -lc "cd '/mnt/c/Users/Ali_h/OneDrive/Documents/Macbook-Pro-Tracker' && python3 tracker.py"
