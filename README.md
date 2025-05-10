# CocktailDB

A serverless cocktail database application with SQLite on AWS Lambda.

## Database Architecture

This project uses a SQLite database stored on an Amazon EFS volume that is mounted to Lambda functions. The database is automatically created and initialized during stack deployment.

### Database Initialization Process

1. During deployment, the CloudFormation stack creates an EFS file system that will store the SQLite database
2. The `SchemaDeployFunction` Lambda:
   - Writes the schema.sql file to the EFS volume
   - Creates a new SQLite database on the EFS volume
   - Runs the SQL statements to initialize the database schema
3. The `DBInitLambda` function is provided as a utility to manually reinitialize the database if needed

### Database Access

The main `CocktailLambda` function handles API requests and interacts with the SQLite database on the EFS volume.

## Development

### Modifying the Database Schema

1. Edit the `cocktaildb/schema.sql` file with your schema changes
2. Redeploy the stack to apply the changes
   - By default, existing databases are not overwritten during updates
   - To force recreation of the database, set the `ForceInit` parameter to "true" in the `SchemaDeployResource`

### Manual Database Operations

You can manually reinitialize or update the database using the `SchemaDeployFunction`. This is useful for applying new migrations or resetting the database.

**To force reinitialization or apply a new schema/migration:**

You have a few options to provide the schema/migration `.sql` file content:

1.  **Directly in the payload (`SchemaContent`):** For smaller schema files, you can pass the content directly.
2.  **Via an S3 object (`SchemaS3Bucket` and `SchemaS3Key`):** For larger files, or for a more robust workflow, upload your `.sql` file to an S3 bucket and pass the bucket and key.
3.  **Fallback to packaged `schema.sql`:** If neither of the above is provided, the function will attempt to use the `schema.sql` file packaged with the Lambda function itself (located in `schema-deploy/schema.sql`). This is the default behavior if you don't specify schema input.

**Example `aws lambda invoke` command (using `SchemaContent`):**

```powershell
# Prepare your SQL content (e.g., read from a file into a variable in your shell, or paste directly)
# For this example, let's assume your SQL is: "CREATE TABLE NewTable (ID INT PRIMARY KEY);"
# Remember to escape quotes if your SQL content has them, depending on your shell.

aws lambda invoke --function-name YOUR_SCHEMA_DEPLOY_FUNCTION_NAME \
  --payload '{
    "RequestType": "Create",
    "StackId": "arn:aws:cloudformation:us-east-1:123456789012:stack/cocktaildb/fake-stack-id",
    "RequestId": "manual-invoke-$(uuidgen)", # Or any unique string
    "LogicalResourceId": "SchemaDeployResource",
    "ResourceProperties": {
      "DBName": "cocktaildb",
      "ForceInit": "true",
      "SchemaContent": "CREATE TABLE IF NOT EXISTS ExampleManualTable (ID INT PRIMARY KEY, Name TEXT);"
    }
  }' \
  --cli-binary-format raw-in-base64-out output.txt

# To use an S3 object instead, the ResourceProperties would look like:
# "ResourceProperties": {
#   "DBName": "cocktaildb",
#   "ForceInit": "true",
#   "SchemaS3Bucket": "your-s3-bucket-name",
#   "SchemaS3Key": "path/to/your/schema.sql"
# }
```

**Note for Windows/PowerShell users (reading schema from a local file):**

For a more streamlined way to apply migrations or reinitialize the database using a local SQL file, you can use the `scripts\apply-migration.ps1` PowerShell script.

This script handles:
- Reading your SQL file content.
- Constructing the correct JSON payload for the Lambda function.
- Invoking the `SchemaDeployFunction` Lambda.
- Writing the payload to a temporary file to avoid issues with special characters and command-line length limits.
- Ensuring the temporary file is written in UTF-8 without a Byte Order Mark (BOM).

**Using the `apply-migration.ps1` script:**

1.  Ensure your AWS CLI is configured and authenticated.
2.  Open PowerShell.
3.  Navigate to the `scripts` directory or use the full path to the script.

```powershell
# Example: Apply a migration file
# (If your Lambda function is named 'cocktail-db-prod-schema-deploy', you can omit -LambdaFunctionName)

.\scripts\apply-migration.ps1 -SqlFilePath "..\path\to\your\migration.sql"

# Example: Force reinitialization with a specific SQL file
.\scripts\apply-migration.ps1 -SqlFilePath "..\path\to\your\schema.sql" -ForceInit

# Example: Specifying a different Lambda function name
.\scripts\apply-migration.ps1 -SqlFilePath "..\path\to\your\schema.sql" -LambdaFunctionName "my-custom-deploy-function"
```

**Key Script Parameters:**
-   `-SqlFilePath` (Mandatory): Path to your `.sql` migration or schema file.
-   `-LambdaFunctionName` (Optional): Name of the Schema Deploy Lambda function. Defaults to `cocktail-db-prod-schema-deploy` if your function matches this common naming pattern from the project.
-   `-DbName` (Optional): Name of the database. Defaults to `cocktaildb`.
-   `-ForceInit` (Optional Switch): If present, sets `ForceInit` to `true`, causing the database to be deleted and recreated before applying the schema.
-   `-StackId` (Optional): The CloudFormation Stack ID. Defaults to a placeholder that includes the region and account ID derived from the default Lambda function name.

**PowerShell Execution Policy:**
If you encounter an error about scripts being disabled, you may need to adjust your PowerShell execution policy for the current session. You can bypass it for a single command:
```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\apply-migration.ps1 -SqlFilePath "..\path\to\your\migration.sql"
```
Refer to the script's output and `migration-output.txt` for invocation results.

**Important Notes:**
- Replace `YOUR_SCHEMA_DEPLOY_FUNCTION_NAME` with the actual name of your schema deployment Lambda function (e.g., `cocktail-db-prod-SchemaDeployFunction-XXXXXX`). You can find this in the CloudFormation stack outputs or the Lambda console.
- The `RequestId` should be a unique string for each invocation. Using `uuidgen` (on macOS/Linux) or `[guid]::NewGuid()` (in PowerShell) can generate one.
- Setting `"ForceInit": "true"` will cause the existing database file to be removed and recreated before the schema is applied. If you set it to `"false"` (or omit it) and the database file already exists, the schema will not be applied during an "Update" `RequestType` unless it's a new database creation. For "Create" `RequestType` it always initializes.
- Check `output.txt` and the CloudWatch logs for the Lambda function to see the outcome of the invocation.

## Architecture

This project uses the following AWS services:
- Amazon Aurora PostgreSQL (Serverless v2) for the database
- AWS Lambda for serverless backend logic
- Amazon API Gateway for REST API
- Amazon S3 for static website hosting and image storage
- Amazon CloudFront for content delivery
- AWS Secrets Manager for database credentials

## Prerequisites

- AWS CLI installed and configured with appropriate credentials
- AWS SAM CLI installed (https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Python 3.9 or later
- boto3 Python package (`pip install boto3`)

## Deployment Instructions

You can deploy the application using either the batch script (Windows) or by running the commands manually.

### Windows Deployment (Using deploy.bat)

For Windows users, simply run the deploy.bat script:

```
scripts\deploy.bat
```

This script will:
1. Build the application with AWS SAM
2. Deploy the CloudFormation stack using SAM
3. Upload web content to S3
4. Display the CloudFormation stack outputs

### Manual Deployment

#### 1. Build with SAM

Build the application using AWS SAM:

```bash
sam build --template-file cloudformation/main.yaml
```

This will:
1. Process the CloudFormation template
2. Automatically package Lambda functions
3. Create a deployment-ready template

#### 2. Deploy with SAM

Once the application is built, deploy it with SAM:

```bash
sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name cocktaildb \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

#### 3. Monitor Deployment

You can monitor the deployment progress in the AWS CloudFormation console or using the AWS CLI:

```bash
aws cloudformation describe-stacks --stack-name cocktaildb
```

## Architecture Changes

- **Single Subnet**: The template has been modified to use a single subnet for simplicity.
- **Serverless Application Model**: The project uses AWS SAM for easier serverless application deployment.

## Website Access

After deployment is complete, you can access the website using the CloudFront URL provided in the CloudFormation outputs:

```bash
aws cloudformation describe-stack-outputs --stack-name cocktaildb
```

## API Endpoints

The API includes the following endpoints:
- `/api/ingredients` - Manage cocktail ingredients
- `/api/recipes` - Manage cocktail recipes
- `/api/units` - Manage measurement units

## License

This project is licensed under the MIT License - see the LICENSE file for details.
