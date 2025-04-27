@echo off
setlocal enabledelayedexpansion

REM Check if we're in the right mamba environment
echo Checking mamba environment...
call conda info --envs | findstr "cocktaildb-312" > nul
if %ERRORLEVEL% neq 0 (
    echo Activating mamba cocktaildb-312 environment...
    call mamba activate cocktaildb-312
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to activate mamba cocktaildb-312 environment
        exit /b 1
    )
    echo Successfully activated mamba cocktaildb-312 environment
) else (
    echo Already in the correct mamba environment
)

REM Change to project root directory
cd %~dp0\..

REM Define stack name
set STACK_NAME=cocktail-db-prod
set REGION=us-east-1

echo Building application with SAM...
sam build --template-file template.yaml --region %REGION%

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
set BUCKET_NAME=
set AWS_CMD=aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?OutputKey=='WebsiteBucketName'].OutputValue" --output text --region %REGION%
for /f "tokens=*" %%i in ('%AWS_CMD%') do (
    set BUCKET_NAME=%%i
)

REM Verify we got a valid bucket name
if "!BUCKET_NAME!"=="" (
    echo Error: Could not retrieve bucket name from CloudFormation outputs
    echo Please check if the stack deployment completed successfully
    exit /b 1
)

echo Found bucket name: !BUCKET_NAME!

REM Upload web content to S3 after deployment
echo Uploading web content to S3 bucket: !BUCKET_NAME!
aws s3 sync src\web\ s3://!BUCKET_NAME!/ --delete --region %REGION%

if %ERRORLEVEL% neq 0 (
    echo Error uploading web content with AWS CLI
    exit /b %ERRORLEVEL%
) else (
    echo Web content uploaded successfully!
)

REM Invalidate CloudFront cache
echo Invalidating CloudFront cache...
set DISTRIBUTION_ID=
set AWS_CMD=aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistribution'].OutputValue" --output text --region %REGION%
for /f "tokens=*" %%i in ('%AWS_CMD%') do (
    set DISTRIBUTION_ID=%%i
)

if not "!DISTRIBUTION_ID!"=="" (
    aws cloudfront create-invalidation --distribution-id !DISTRIBUTION_ID! --paths "/*" --region %REGION%
    echo CloudFront cache invalidation initiated
) else (
    echo Warning: Could not retrieve CloudFront distribution ID
)

echo Getting CloudFormation outputs...
aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs" --output table --region %REGION%

endlocal 