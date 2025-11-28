# CocktailDB

A serverless cocktail database application with SQLite on AWS Lambda.

## Monorepo Structure

This repository contains multiple packages:

- **`packages/barcart/`** - Cocktail analytics algorithms (recipe similarity, ingredient distance metrics)
  - Install: `pip install -e packages/barcart`
  - Used by analytics Lambda and local analysis scripts
  - Independent package with own tests and documentation

See individual package READMEs for details.

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

## Local Development

For testing frontend changes locally without deploying:

```bash
# Generate local config (points to dev API)
./scripts/local-config.sh

# Start local server
./scripts/serve.sh

# Open browser to http://localhost:8000
```

**Features:**
- Test UI/UX changes instantly
- No deployment required
- Uses dev backend API and auth
- Static file serving via Python http.server

**For enhanced development with live-reload:**
```bash
npx live-server src/web --port=8000
```

See [docs/local-development.md](docs/local-development.md) for detailed setup, troubleshooting, and advanced usage.

## Deployment Instructions

You can deploy the application using either the batch script (Windows) or by running the commands manually.


## License

This project is licensed under the MIT License - see the LICENSE file for details.
