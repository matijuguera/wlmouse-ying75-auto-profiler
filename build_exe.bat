@echo off
rem Builds dist\WLMouseAutoProfiler.exe (standalone, no Python needed to run it)
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name WLMouseAutoProfiler --icon logo.ico ^
    --add-data "logo.jpg;." --add-data "logo.ico;." ^
    step3_auto_profiler.py
