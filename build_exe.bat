@echo off
REM Builds a single-file Windows program: dist\ResumeJobAnalyzer.exe
REM Run this from the project folder (the one that contains app.py).

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :failed

python -m PyInstaller --noconfirm --onefile --windowed --name ResumeJobAnalyzer ^
  --add-data "skills.json;." --add-data "resources.json;." ^
  --collect-data docx app.py
if errorlevel 1 goto :failed

echo.
echo Done. Your program is here:  dist\ResumeJobAnalyzer.exe
goto :end

:failed
echo.
echo The build failed. Read the messages above.

:end
pause
