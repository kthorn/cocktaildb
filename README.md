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


## License

This project is licensed under the MIT License - see the LICENSE file for details.
