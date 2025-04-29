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

You can manually reinitialize the database using the `DBInitLambda` function:

```powershell
# Force reinitialization of the database
aws lambda invoke --function-name cocktail-db-prod-schema-deploy --payload "{\"RequestType\": \"Create\", \"StackId\": \"arn:aws:cloudformation:us-east-1:123456789012:stack/cocktaildb/12345678-1234-1234-1234-123456789012\", \"RequestId\": \"12345678-1234-1234-1234-123456789012\", \"LogicalResourceId\": \"SchemaDeployResource\", \"ResourceProperties\": {\"DBName\": \"cocktaildb\", \"ForceInit\": \"true\"}}" --cli-binary-format raw-in-base64-out output.txt
```

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
