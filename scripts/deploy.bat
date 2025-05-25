@echo off
setlocal enabledelayedexpansion

REM Parse arguments
set TARGET_ENV=%1
set NO_BUILD=0

REM Default to dev if no environment specified
if "!TARGET_ENV!"=="" (
    echo No environment specified, defaulting to 'dev'.
    set TARGET_ENV=dev
) else if "!TARGET_ENV!"=="--no-build" (
    echo Error: Please specify environment first, e.g., dev --no-build
    exit /b 1
) else (
    echo Target environment: !TARGET_ENV!
)

REM Check for no-build flag
if "%2"=="--no-build" (
    set NO_BUILD=1
    echo Skipping SAM build and deploy steps...
)

REM Validate environment
if not "!TARGET_ENV!"=="dev" if not "!TARGET_ENV!"=="prod" (
    echo Error: Invalid environment '!TARGET_ENV!'. Use 'dev' or 'prod'.
    exit /b 1
)

REM Validate HOSTED_ZONE_ID for prod deployments
if "!TARGET_ENV!"=="prod" (
    if "%HOSTED_ZONE_ID%"=="" (
        echo ERROR: HOSTED_ZONE_ID environment variable required for prod deployment.
        echo Please set the HOSTED_ZONE_ID environment variable before running this script.
        exit /b 1
    )
) else (
    if "%HOSTED_ZONE_ID%"=="" (
        echo WARNING: HOSTED_ZONE_ID not set for dev. Using placeholder.
        set HOSTED_ZONE_ID=NONE
    )
)

REM Setup environment
call mamba activate cocktaildb-312
cd %~dp0\..

REM Define deployment variables
set STACK_NAME=cocktail-db-!TARGET_ENV!
set REGION=us-east-1
set DB_NAME_PARAM=cocktaildb-!TARGET_ENV!
set USER_POOL_NAME_PARAM=CocktailDB-UserPool-!TARGET_ENV!
set PARAM_OVERRIDES=Environment=!TARGET_ENV! HostedZoneId=%HOSTED_ZONE_ID% DatabaseName=!DB_NAME_PARAM! UserPoolName=!USER_POOL_NAME_PARAM!

echo Stack name: !STACK_NAME!

REM Build and deploy with SAM (if not skipped)
if %NO_BUILD%==0 (
    echo Building application with SAM...
    sam build --template-file template.yaml --region %REGION%
    if %ERRORLEVEL% neq 0 (
        echo Error building with SAM
        exit /b %ERRORLEVEL%
    )

    echo Deploying with SAM to !TARGET_ENV! environment...
    sam deploy ^
        --template-file .aws-sam\build\template.yaml ^
        --stack-name !STACK_NAME! ^
        --parameter-overrides !PARAM_OVERRIDES! ^
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND ^
        --no-fail-on-empty-changeset ^
        --resolve-s3 ^
        --on-failure DELETE ^
        --region %REGION%

    if %ERRORLEVEL% neq 0 (
        echo Error deploying with SAM to !TARGET_ENV!
        exit /b %ERRORLEVEL%
    )

    echo Deployment to !TARGET_ENV! complete!
) else (
    echo Skipped SAM build and deploy steps for !STACK_NAME!
)

REM Get S3 bucket name for web content
echo Getting S3 bucket name...
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name !STACK_NAME! --query "Stacks[0].Outputs[?OutputKey=='WebsiteBucketName'].OutputValue" --output text --region %REGION%') do (
    set BUCKET_NAME=%%i
)

if "!BUCKET_NAME!"=="" (
    echo Error: Could not retrieve bucket name from CloudFormation outputs for stack !STACK_NAME!
    echo Please check if the stack deployment completed successfully
    exit /b 1
)

echo Found bucket name: !BUCKET_NAME!

REM Generate config.js using Python script
echo Generating config.js...
python scripts\generate_config.py !STACK_NAME! !TARGET_ENV! --region %REGION%
if %ERRORLEVEL% neq 0 (
    echo Error generating config.js
    exit /b %ERRORLEVEL%
)

REM Upload web content to S3
echo Uploading web content to S3...
aws s3 sync src\web\ s3://!BUCKET_NAME!/ --delete --region %REGION%
if %ERRORLEVEL% neq 0 (
    echo Error uploading web content
    exit /b %ERRORLEVEL%
)

echo Web content uploaded successfully!

REM Invalidate CloudFront cache
echo Invalidating CloudFront cache...
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name !STACK_NAME! --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistribution'].OutputValue" --output text --region %REGION%') do (
    set DISTRIBUTION_ID=%%i
)

if not "!DISTRIBUTION_ID!"=="" (
    aws cloudfront create-invalidation --distribution-id !DISTRIBUTION_ID! --paths "/*" --region %REGION%
    echo CloudFront cache invalidation initiated!
) else (
    echo Warning: Could not retrieve CloudFront distribution ID
)

REM Display final CloudFormation outputs
echo.
echo CloudFormation stack outputs:
aws cloudformation describe-stacks --stack-name !STACK_NAME! --query "Stacks[0].Outputs" --output table --region %REGION%

echo.
echo Deployment completed successfully!

endlocal 