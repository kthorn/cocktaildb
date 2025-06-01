# Requires -Modules AWS.Tools.Installer, AWS.Tools.Lambda

param(
    [Parameter(Mandatory=$true)]
    [string]$SqlFilePath,

    [Parameter(Mandatory=$false)]
    [ValidateSet("dev", "prod")]
    [string]$Environment = "dev",

    [Parameter(Mandatory=$false)]
    [string]$LambdaFunctionName = "",

    [Parameter(Mandatory=$false)]
    [string]$DbName = "",

    [Parameter(Mandatory=$false)]
    [switch]$ForceInit = $false,

    [Parameter(Mandatory=$false)]
    [string]$StackId = "",

    [Parameter(Mandatory=$false)]
    [string]$LogicalResourceId = "SchemaDeployResource",

    [Parameter(Mandatory=$false)]
    [string]$Region = "us-east-1"
)

# Set environment-specific defaults if not provided
$stackName = "cocktail-db-$Environment"

if (-not $LambdaFunctionName) {
    $LambdaFunctionName = "$stackName-schema-deploy"
}

if (-not $DbName) {
    $DbName = "cocktaildb-$Environment"
}

if (-not $StackId) {
    # Try to get actual stack ID from CloudFormation
    try {
        $stackInfo = aws cloudformation describe-stacks --stack-name $stackName --region $Region --query "Stacks[0].StackId" --output text 2>$null
        if ($stackInfo -and $stackInfo -ne "None") {
            $StackId = $stackInfo
            Write-Host "Retrieved stack ID from CloudFormation: $StackId"
        } else {
            # Fallback to placeholder format
            $accountId = aws sts get-caller-identity --query "Account" --output text 2>$null
            if ($accountId -and $accountId -ne "None") {
                $StackId = "arn:aws:cloudformation:${Region}:${accountId}:stack/${stackName}/placeholder-stack-id"
                Write-Host "Using placeholder stack ID: $StackId"
            } else {
                $StackId = "arn:aws:cloudformation:${Region}:123456789012:stack/${stackName}/placeholder-stack-id"
                Write-Host "Using default placeholder stack ID: $StackId"
            }
        }
    } catch {
        # Fallback to placeholder format
        $StackId = "arn:aws:cloudformation:${Region}:123456789012:stack/${stackName}/placeholder-stack-id"
        Write-Host "Using fallback placeholder stack ID: $StackId"
    }
}

Write-Host "=== Migration Configuration ==="
Write-Host "Environment: $Environment"
Write-Host "Stack Name: $stackName"
Write-Host "Lambda Function: $LambdaFunctionName"
Write-Host "Database Name: $DbName"
Write-Host "Region: $Region"
Write-Host "Force Init: $($ForceInit.IsPresent)"
Write-Host "=============================="

# Check if SQL file exists
if (-not (Test-Path $SqlFilePath -PathType Leaf)) {
    Write-Error "Error: SQL file not found at '$SqlFilePath'"
    exit 1
}

# Read SQL content
Write-Host "Reading SQL content from '$SqlFilePath'..."
$rawSqlContent = Get-Content -Path $SqlFilePath -Raw
# Ensure $sqlContent is treated as a plain string for JSON conversion
$sqlContent = [string]$rawSqlContent

# Generate a unique RequestId
$requestId = "manual-invoke-$([guid]::NewGuid())"

# Determine ForceInit string value
$forceInitString = $ForceInit.IsPresent.ToString().ToLower()

# Construct the payload
$payloadObject = @{
  RequestType = "Update" # Using Update, as Create is usually for initial CFN deployment
  StackId = $StackId
  RequestId = $requestId
  LogicalResourceId = $LogicalResourceId
  ResourceProperties = @{
    DBName = $DbName
    ForceInit = $forceInitString
    SchemaContent = $sqlContent
  }
}

$payloadJsonString = $payloadObject | ConvertTo-Json -Compress -Depth 5

Write-Host "Prepared Payload JSON String:"
Write-Host $payloadJsonString

$outputFile = "migration-output.txt"
$tempPayloadFile = $null

Write-Host "Invoking Lambda function '$LambdaFunctionName'..."

try {
    # Create a temporary file for the payload
    $tempPayloadFile = New-TemporaryFile
    # Use .NET method to write UTF-8 without BOM, being very explicit
    $utf8NoBomEncoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tempPayloadFile.FullName, $payloadJsonString, $utf8NoBomEncoding)

    Write-Host "Payload written to temporary file: $($tempPayloadFile.FullName)"

    aws lambda invoke --function-name $LambdaFunctionName `
      --payload "file://$($tempPayloadFile.FullName)" `
      --cli-binary-format raw-in-base64-out $outputFile

    Write-Host "Lambda invocation command executed."
    Write-Host "Output (if any) written to '$outputFile'. Check this file for details."

    if (Test-Path $outputFile) {
        $outputContent = Get-Content $outputFile -Raw
        Write-Host "--- Content of $outputFile ---"
        Write-Host $outputContent
        Write-Host "-------------------------------"
    }
} catch {
    Write-Error "Error during Lambda invocation: $_"
    # It's good practice to still try and clean up the temp file in case of an error before exiting
    if ($tempPayloadFile -and (Test-Path $tempPayloadFile.FullName)) {
        Remove-Item -Path $tempPayloadFile.FullName -Force -ErrorAction SilentlyContinue
        Write-Host "Cleaned up temporary payload file: $($tempPayloadFile.FullName)"
    }
    exit 1
} finally {
    # Ensure temporary file is cleaned up if it exists
    if ($tempPayloadFile -and (Test-Path $tempPayloadFile.FullName)) {
        Remove-Item -Path $tempPayloadFile.FullName -Force -ErrorAction SilentlyContinue
        Write-Host "Cleaned up temporary payload file in finally block: $($tempPayloadFile.FullName)"
    }
}

Write-Host "Script finished." 