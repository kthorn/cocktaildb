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
    --resolve-s3 ^
    --on-failure DELETE ^
    --region %REGION% 

if %ERRORLEVEL% neq 0 (
    echo Error deploying with SAM
    exit /b %ERRORLEVEL%
)

echo Deployment complete!

REM Get website bucket name from CloudFormation outputs
echo Getting S3 bucket name...
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?OutputKey=='WebsiteBucketName'].OutputValue" --output text --region %REGION%') do (
    set BUCKET_NAME=%%i
)

REM Upload web content to S3 after deployment
echo Uploading web content to S3 bucket: !BUCKET_NAME!
aws s3 sync src\web\ s3://!BUCKET_NAME!/ --delete --region %REGION%

if %ERRORLEVEL% neq 0 (
    echo Error uploading web content with AWS CLI
    exit /b %ERRORLEVEL%
) else (
    echo Web content uploaded successfully!
)

echo Getting CloudFormation outputs...
aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs" --output table --region %REGION%

endlocal 