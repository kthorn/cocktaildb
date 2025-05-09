# Requires -Modules AWS.Tools.Installer, AWS.Tools.Lambda

param(
    [Parameter(Mandatory=$true)]
    [string]$SqlFilePath,

    [Parameter(Mandatory=$false)]
    [string]$LambdaFunctionName = "cocktail-db-prod-schema-deploy",

    [Parameter(Mandatory=$false)]
    [string]$DbName = "cocktaildb",

    [Parameter(Mandatory=$false)]
    [switch]$ForceInit = $false,

    [Parameter(Mandatory=$false)]
    [string]$StackId = "arn:aws:cloudformation:us-east-1:732940910135:stack/cocktail-db-prod/e130ecf0-247c-11f0-9c66-122677aad09d",

    [Parameter(Mandatory=$false)]
    [string]$LogicalResourceId = "SchemaDeployResource"
)

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