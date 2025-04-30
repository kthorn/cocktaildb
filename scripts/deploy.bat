@echo off
setlocal enabledelayedexpansion

REM Check for no-build flag
set NO_BUILD=0
if "%1"=="--no-build" (
    set NO_BUILD=1
    echo Skipping SAM build and deploy steps...
)

call mamba activate cocktaildb-312

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

REM Get API endpoint URL from CloudFormation outputs
echo Getting API endpoint URL...
set API_URL=
set AWS_CMD=aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text --region %REGION%
for /f "tokens=*" %%i in ('%AWS_CMD%') do (
    set API_URL=%%i
)

REM Get Cognito User Pool ID
echo Getting Cognito User Pool ID...
set USER_POOL_ID=
set AWS_CMD=aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text --region %REGION%
for /f "tokens=*" %%i in ('%AWS_CMD%') do (
    set USER_POOL_ID=%%i
)

REM Get Cognito User Pool Client ID
echo Getting Cognito User Pool Client ID...
set CLIENT_ID=
set AWS_CMD=aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" --output text --region %REGION%
for /f "tokens=*" %%i in ('%AWS_CMD%') do (
    set CLIENT_ID=%%i
)

REM Get Cognito Domain URL
echo Getting Cognito Domain URL...
set COGNITO_DOMAIN=
set AWS_CMD=aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?OutputKey=='CognitoDomainURL'].OutputValue" --output text --region %REGION%
for /f "tokens=*" %%i in ('%AWS_CMD%') do (
    set COGNITO_DOMAIN=%%i
)

REM Verify we got a valid API URL
if "!API_URL!"=="" (
    echo Warning: Could not retrieve API URL from CloudFormation outputs
) else (
    echo Found API URL: !API_URL!
    
    REM Update config.js with the current API URL and Cognito information
    echo Updating config.js with current API URL and Cognito information...
    (
        echo // Configuration for the Cocktail Database application
        echo const config = {
        echo     // API endpoint
        echo     apiUrl: '!API_URL!',
        echo.
        echo     // Cognito configuration
        echo     userPoolId: '!USER_POOL_ID!',
        echo     clientId: '!CLIENT_ID!',
        echo     cognitoDomain: '!COGNITO_DOMAIN!',
        echo.
        echo     // General settings
        echo     appName: 'Cocktail Database'
        echo };
        echo.
        echo // Export the configuration
        echo export default config; 
    ) > src\web\js\config.js
    echo config.js updated successfully
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