# Deployment Scripts

This directory contains scripts for deploying the Cocktail Database application.

## Files

- `deploy.bat` - Main deployment script for Windows
- `generate_config.py` - Python script for generating config.js from CloudFormation outputs
- `requirements.txt` - Python dependencies for the generate_config.py script

## Usage

### Deploy Script

```bash
# Deploy to dev environment
scripts/deploy.bat dev

# Deploy to prod environment
scripts/deploy.bat prod

# Deploy without rebuilding (useful for testing)
scripts/deploy.bat dev --no-build
```

### Config Generation Script

The Python script is automatically called by the deploy script, but can also be run standalone:

```bash
# Generate config.js for dev environment
python scripts/generate_config.py cocktail-db-dev dev

# Generate config.js for prod environment with custom region
python scripts/generate_config.py cocktail-db-prod prod --region us-west-2

# Generate config.js with custom output path
python scripts/generate_config.py cocktail-db-dev dev --output custom/path/config.js
```

## Dependencies

Before using the Python script, install the required dependencies:

```bash
pip install -r scripts/requirements.txt
```

Or if using mamba/conda (as used in the deploy script):

```bash
mamba activate cocktaildb-312
pip install -r scripts/requirements.txt
```

## What the Config Script Does

The `generate_config.py` script:

1. Retrieves configuration values from CloudFormation stack outputs:
   - API endpoint URL
   - Cognito User Pool ID
   - Cognito User Pool Client ID
   - Cognito Domain URL
   - Application URL (CloudFront or custom domain based on environment)

2. Validates all values and checks for problematic characters

3. Generates the `src/web/js/config.js` file with the correct configuration

4. Handles environment-specific logic (dev vs prod) for determining the correct application URL

This approach is much cleaner and more maintainable than the complex batch file logic that was previously used. 