@echo off
setlocal enabledelayedexpansion

REM Change to project root directory
cd %~dp0\..

REM Define stack name
set STACK_NAME=cocktail-db-prod
set REGION=us-east-1

echo Building application with SAM...
sam build --template-file cloudformation\main.yaml --region %REGION%

if %ERRORLEVEL% neq 0 (
    echo Error building with SAM
    exit /b %ERRORLEVEL%
)

echo Deploying with SAM to production environment...
sam deploy ^
    --template-file .aws-sam\build\template.yaml ^
    --stack-name %STACK_NAME% ^
    --parameter-overrides Environment=prod ^
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM ^
    --no-fail-on-empty-changeset ^
    --region %REGION%

if %ERRORLEVEL% neq 0 (
    echo Error deploying with SAM
    exit /b %ERRORLEVEL%
)

echo Deployment complete!

REM Upload web content to S3 after deployment
echo Uploading web content to S3...
python scripts\upload_web_content.py

echo Getting CloudFormation outputs...
aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs" --output table --region %REGION%

endlocal 