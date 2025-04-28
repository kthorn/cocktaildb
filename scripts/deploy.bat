@echo off
setlocal enabledelayedexpansion

REM Check for no-build flag
set NO_BUILD=0
if "%1"=="--no-build" (
    set NO_BUILD=1
    echo Skipping SAM build and deploy steps...
)

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

if %NO_BUILD%==0 (
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
) else (
    echo Skipped SAM build and deploy steps
)

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

REM Get required environment variables for database initialization
echo Setting up database environment variables...

REM Get DB Cluster ARN
set DB_CLUSTER_ARN=
for /f "tokens=*" %%i in ('aws rds describe-db-clusters --query "DBClusters[?contains(DBClusterIdentifier, '%STACK_NAME%')].DBClusterArn" --output text --region %REGION%') do (
    set DB_CLUSTER_ARN=%%i
)
echo DB_CLUSTER_ARN=!DB_CLUSTER_ARN!

REM Get Secret ARN for database credentials 
set DB_SECRET_ARN=
for /f "tokens=*" %%i in ('aws secretsmanager list-secrets --query "SecretList[?Name=='%STACK_NAME%-db-creds'].ARN" --output text --region %REGION%') do (
    set DB_SECRET_ARN=%%i
)
echo DB_SECRET_ARN=!DB_SECRET_ARN!

REM Set database name
set DB_NAME=cocktaildb
echo DB_NAME=!DB_NAME!

REM Export environment variables for use with initialize_db.py
set DB_CLUSTER_ARN=!DB_CLUSTER_ARN!
set DB_SECRET_ARN=!DB_SECRET_ARN!
set DB_NAME=!DB_NAME!

REM Also set for future command windows
setx DB_CLUSTER_ARN "!DB_CLUSTER_ARN!"
setx DB_SECRET_ARN "!DB_SECRET_ARN!"
setx DB_NAME "!DB_NAME!"

echo Environment variables set for database initialization
echo To run the database initialization script:
echo python scripts/initialize_db.py

echo Getting CloudFormation outputs...
aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs" --output table --region %REGION%

endlocal 