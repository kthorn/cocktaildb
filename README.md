# CocktailDB

A cocktail database application hosted on EC2 with FastAPI and PostgreSQL.

## Monorepo Structure

This repository contains multiple packages:

- **`packages/barcart/`** - Cocktail analytics algorithms (recipe similarity, ingredient distance metrics)
  - Install: `pip install -e packages/barcart`
  - Used by analytics jobs and local analysis scripts
  - Independent package with own tests and documentation

See individual package READMEs for details.

## Architecture

This project uses the following AWS services:
- Amazon EC2 for the FastAPI backend
- PostgreSQL for the database
- Amazon Cognito for authentication
- Amazon S3 for analytics and backup storage
- AWS IAM for instance roles and access control

## Prerequisites

- AWS CLI installed and configured with appropriate credentials
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
