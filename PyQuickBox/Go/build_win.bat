@echo off
setlocal enabledelayedexpansion

set "APP_NAME=PyQuickBox"
set "ICON_PNG=Icon.png"
set "ICON_ICO=Icon.ico"

echo ----------------------------------------------------
echo  PyQuickBox Robust Windows Builder
echo ----------------------------------------------------

:: 1. Check Build Environment
echo [CHECK] Checking Go...
where go >nul 2>nul
if %errorlevel% neq 0 goto :NoGo

echo [CHECK] Checking GCC...
where gcc >nul 2>nul
if %errorlevel% neq 0 goto :NoGCC

:: 2. Install resource embedding tool (rsrc)
echo.
echo [STEP 1/4] Checking tools...
where rsrc >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing rsrc...
    go install github.com/akavel/rsrc@latest
)

:: 3. Convert Icon using helper script (icon_gen.go)
echo.
echo [STEP 2/4] Converting Icon...
if exist icon_gen.go (
    go run icon_gen.go
) else (
    echo [WARNING] icon_gen.go not found. Skipping conversion.
    if not exist %ICON_ICO% (
        echo [ERROR] No Icon.ico found. Building without icon.
    )
)

:: 4. Embed Icon
echo.
echo [STEP 3/4] Embedding Resource...
if exist %ICON_ICO% (
    rsrc -ico %ICON_ICO% -o rsrc.syso
) else (
    echo [WARNING] Skipping icon embedding.
)

:: 5. Build
echo.
echo [STEP 4/4] Building Application...
go mod tidy
:: -H=windowsgui hides console, -s -w strips debug info
go build -ldflags="-H=windowsgui -s -w" -v -o %APP_NAME%.exe .

if %errorlevel% equ 0 goto :Success
goto :Fail

:Success
echo.
echo ----------------------------------------------------
echo [SUCCESS] Build Complete: %APP_NAME%.exe
echo ----------------------------------------------------
:: Cleanup
if exist rsrc.syso del rsrc.syso
if exist %ICON_ICO% del %ICON_ICO%
pause
exit /b 0

:NoGo
echo [ERROR] Go not installed.
pause
exit /b 1

:NoGCC
echo [ERROR] GCC not installed.
pause
exit /b 1

:Fail
echo [FAILURE] Build Failed.
pause
exit /b 1
