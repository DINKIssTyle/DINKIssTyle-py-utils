@echo off
set APP_NAME=PyQuickBox
set APP_ID=com.dinkisstyle.pyquickbox
set ICON=Icon.png

echo Building %APP_NAME% for Windows...

where fyne >nul 2>nul
if %errorlevel% neq 0 (
    echo Fyne CLI not found. Installing...
    go install fyne.io/fyne/v2/cmd/fyne@latest
    set PATH=%PATH%;%USERPROFILE%\go\bin
)

echo Packaging...
fyne package -os windows -icon %ICON% -name %APP_NAME% -appID %APP_ID%

if %errorlevel% equ 0 (
    echo.
    echo ----------------------------------------
    echo Build Complete: %APP_NAME%.exe
    echo ----------------------------------------
) else (
    echo.
    echo Build Failed. Please check errors above.
)
pause
