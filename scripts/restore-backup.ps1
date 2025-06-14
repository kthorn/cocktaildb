# Database restore script for CocktailDB
# Downloads backups from S3 and restores them to target environment

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("dev", "prod")]
    [string]$TargetEnvironment = "dev",

    [Parameter(Mandatory=$false)]
    [ValidateSet("dev", "prod")]
    [string]$SourceEnvironment = "prod",

    [Parameter(Mandatory=$false)]
    [string]$BackupFile = "latest",

    [Parameter(Mandatory=$false)]
    [string]$BackupBucket = "",

    [Parameter(Mandatory=$false)]
    [string]$Region = "us-east-1",

    [Parameter(Mandatory=$false)]
    [switch]$ListBackups = $false,

    [Parameter(Mandatory=$false)]
    [switch]$DryRun = $false,

    [Parameter(Mandatory=$false)]
    [switch]$Force = $false
)

# Set environment-specific defaults
$sourceStackName = "cocktail-db-$SourceEnvironment"
$targetStackName = "cocktail-db-$TargetEnvironment"

if (-not $BackupBucket) {
    # Use the actual backup bucket naming pattern from the CloudFormation template
    $BackupBucket = "cocktail-db-$SourceEnvironment-db-backups"
}

Write-Host "=== Database Restore Configuration ==="
Write-Host "Source Environment: $SourceEnvironment"
Write-Host "Target Environment: $TargetEnvironment"
Write-Host "Backup Bucket: $BackupBucket"
Write-Host "Backup File: $BackupFile"
Write-Host "Region: $Region"
Write-Host "Dry Run: $($DryRun.IsPresent)"
Write-Host "====================================="

# Function to list available backups
function Get-AvailableBackups {
    param($Bucket, $Region)
    
    Write-Host "Listing available backups in s3://$Bucket..."
    
    try {
        $backups = aws s3 ls "s3://$Bucket/" --region $Region | Where-Object { $_ -match "backup-.*\.db$" } | ForEach-Object {
            if ($_ -match "(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\d+)\s+(backup-.+\.db)") {
                [PSCustomObject]@{
                    Date = [DateTime]::Parse($matches[1])
                    Size = [int]$matches[2]
                    FileName = $matches[3]
                    SizeFormatted = Format-FileSize $matches[2]
                }
            }
        } | Sort-Object Date -Descending
        
        if ($backups) {
            Write-Host "`nAvailable backups (newest first):"
            Write-Host "Date                Size        File Name"
            Write-Host "---                 ----        ---------"
            foreach ($backup in $backups) {
                Write-Host "$($backup.Date.ToString('yyyy-MM-dd HH:mm:ss')) $($backup.SizeFormatted.PadLeft(10)) $($backup.FileName)"
            }
            return $backups
        } else {
            Write-Host "No backups found in bucket."
            return @()
        }
    } catch {
        Write-Error "Error listing backups: $_"
        return @()
    }
}

# Function to format file size
function Format-FileSize {
    param([long]$Size)
    
    if ($Size -gt 1GB) {
        return "{0:N2} GB" -f ($Size / 1GB)
    } elseif ($Size -gt 1MB) {
        return "{0:N2} MB" -f ($Size / 1MB)
    } elseif ($Size -gt 1KB) {
        return "{0:N2} KB" -f ($Size / 1KB)
    } else {
        return "$Size B"
    }
}

# Function to get the latest backup
function Get-LatestBackup {
    param($Backups)
    
    if ($Backups) {
        return $Backups[0].FileName
    } else {
        return $null
    }
}

# Function to validate backup file exists
function Test-BackupExists {
    param($Bucket, $BackupFile, $Region)
    
    try {
        $result = aws s3 ls "s3://$Bucket/$BackupFile" --region $Region
        return $result -ne ""
    } catch {
        return $false
    }
}

# Function to restore database using schema deploy function
function Restore-Database {
    param($BackupBucket, $BackupFile, $TargetEnv, $Region, $IsDryRun)
    
    $targetStackName = "cocktail-db-$TargetEnv"
    $lambdaFunctionName = "$targetStackName-schema-deploy"
    $dbName = "cocktaildb-$TargetEnv"
    
    # Generate a unique RequestId
    $requestId = "restore-invoke-$([guid]::NewGuid())"
    
    # Get stack ID
    try {
        $stackId = aws cloudformation describe-stacks --stack-name $targetStackName --region $Region --query "Stacks[0].StackId" --output text
        if (-not $stackId -or $stackId -eq "None") {
            throw "Could not retrieve stack ID"
        }
    } catch {
        $accountId = aws sts get-caller-identity --query "Account" --output text
        $stackId = "arn:aws:cloudformation:${Region}:${accountId}:stack/${targetStackName}/placeholder-stack-id"
        Write-Host "Using placeholder stack ID: $stackId"
    }
    
    # Construct the payload for restoration
    $payloadObject = @{
        RequestType = "Update"
        StackId = $stackId
        RequestId = $requestId
        LogicalResourceId = "SchemaDeployResource"
        ResourceProperties = @{
            DBName = $dbName
            ForceInit = "true"  # Always force init when restoring
            RestoreFromS3 = "true"  # Custom flag to indicate restoration
            BackupS3Bucket = $BackupBucket
            BackupS3Key = $BackupFile
        }
    }
    
    $payloadJsonString = $payloadObject | ConvertTo-Json -Compress -Depth 5
    
    if ($IsDryRun) {
        Write-Host "`n=== DRY RUN - Would execute the following ==="
        Write-Host "Lambda Function: $lambdaFunctionName"
        Write-Host "Payload:"
        Write-Host $payloadJsonString
        Write-Host "============================================"
        return $true
    }
    
    Write-Host "`nRestoring database from backup..."
    Write-Host "Target Lambda: $lambdaFunctionName"
    Write-Host "Backup: s3://$BackupBucket/$BackupFile"
    
    $outputFile = "restore-output.txt"
    $tempPayloadFile = $null
    
    try {
        # Create a temporary file for the payload
        $tempPayloadFile = New-TemporaryFile
        $utf8NoBomEncoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempPayloadFile.FullName, $payloadJsonString, $utf8NoBomEncoding)
        
        Write-Host "Invoking Lambda function for database restoration..."
        
        aws lambda invoke --function-name $lambdaFunctionName `
          --payload "file://$($tempPayloadFile.FullName)" `
          --cli-binary-format raw-in-base64-out $outputFile --region $Region
        
        Write-Host "Restoration command executed."
        Write-Host "Output written to '$outputFile'. Check this file for details."
        
        if (Test-Path $outputFile) {
            $outputContent = Get-Content $outputFile -Raw
            Write-Host "--- Restoration Result ---"
            Write-Host $outputContent
            Write-Host "-------------------------"
            
            # Check if restoration was successful
            $outputJson = $outputContent | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($outputJson -and $outputJson.errorMessage) {
                Write-Error "Restoration failed: $($outputJson.errorMessage)"
                return $false
            } else {
                Write-Host "Database restoration completed successfully!" -ForegroundColor Green
                return $true
            }
        }
        
        return $true
        
    } catch {
        Write-Error "Error during restoration: $_"
        return $false
    } finally {
        # Cleanup
        if ($tempPayloadFile -and (Test-Path $tempPayloadFile.FullName)) {
            Remove-Item -Path $tempPayloadFile.FullName -Force -ErrorAction SilentlyContinue
        }
    }
}

# Main execution
try {
    # List backups if requested
    if ($ListBackups) {
        Get-AvailableBackups -Bucket $BackupBucket -Region $Region
        exit 0
    }
    
    # Get available backups
    $availableBackups = Get-AvailableBackups -Bucket $BackupBucket -Region $Region
    
    if (-not $availableBackups) {
        Write-Error "No backups available in bucket $BackupBucket"
        exit 1
    }
    
    # Determine which backup to restore
    $backupToRestore = ""
    if ($BackupFile -eq "latest") {
        $backupToRestore = Get-LatestBackup -Backups $availableBackups
        Write-Host "`nUsing latest backup: $backupToRestore"
    } else {
        $backupToRestore = $BackupFile
        if (-not (Test-BackupExists -Bucket $BackupBucket -BackupFile $backupToRestore -Region $Region)) {
            Write-Error "Specified backup file '$backupToRestore' not found in bucket"
            exit 1
        }
        Write-Host "`nUsing specified backup: $backupToRestore"
    }
    
    # Safety check for prod restoration
    if ($TargetEnvironment -eq "prod" -and -not $Force) {
        Write-Host "`nWARNING: You are about to restore data to the PRODUCTION environment!" -ForegroundColor Red
        Write-Host "This will OVERWRITE the current production database!" -ForegroundColor Red
        Write-Host "Use -Force to bypass this confirmation." -ForegroundColor Yellow
        
        $confirmation = Read-Host "Type 'RESTORE PROD' to confirm"
        if ($confirmation -ne "RESTORE PROD") {
            Write-Host "Restoration cancelled."
            exit 0
        }
    }
    
    # Perform the restoration
    $success = Restore-Database -BackupBucket $BackupBucket -BackupFile $backupToRestore -TargetEnv $TargetEnvironment -Region $Region -IsDryRun $DryRun
    
    if ($success) {
        Write-Host "`nRestore operation completed successfully!" -ForegroundColor Green
        if (-not $DryRun) {
            Write-Host "Database in $TargetEnvironment environment has been restored from backup: $backupToRestore"
        }
    } else {
        Write-Error "Restore operation failed. Check the output above for details."
        exit 1
    }
    
} catch {
    Write-Error "Unexpected error: $_"
    exit 1
}