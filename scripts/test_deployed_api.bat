@echo off
echo Cocktail Database API Tester
echo ===========================

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in PATH. Please install Python 3.x.
    exit /b 1
)

REM Install required packages if not already installed
echo Installing required packages...
pip install requests

REM Ask for the API URL
set /p API_URL="Enter your API Gateway URL (e.g., https://example.execute-api.us-east-1.amazonaws.com/api): "

REM Check if URL is provided
if "%API_URL%"=="" (
    echo No API URL provided. Exiting.
    exit /b 1
)

echo.
echo Which endpoint would you like to test?
echo 1. All endpoints
echo 2. Ingredients endpoint
echo 3. Recipes endpoint
echo 4. Units endpoint
echo 5. Config endpoint
echo.

set /p CHOICE="Enter your choice (1-5): "

set ENDPOINT=all
if "%CHOICE%"=="2" set ENDPOINT=ingredients
if "%CHOICE%"=="3" set ENDPOINT=recipes
if "%CHOICE%"=="4" set ENDPOINT=units
if "%CHOICE%"=="5" set ENDPOINT=config

echo.
echo Testing %ENDPOINT% endpoint(s) at %API_URL%...
echo.

REM Run the test script
python test_api.py --url "%API_URL%" --endpoint %ENDPOINT%

echo.
echo Testing complete.
pause 