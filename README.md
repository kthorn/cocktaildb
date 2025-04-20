# Cocktail Database on AWS

This project implements a serverless cocktail database using AWS services including:
- AWS Lambda for backend processing
- Amazon Aurora Serverless for database storage
- Amazon S3 for static assets and images
- AWS CloudFormation for infrastructure as code

## Project Structure

```
├── cloudformation/         # CloudFormation templates
│   ├── templates/         # Nested stacks and reusable components
│   └── main.yaml         # Main deployment template
├── lambda/               # Lambda function code
│   ├── functions/       # Individual Lambda functions
│   └── layers/          # Lambda layers
├── src/                 # Source code
│   ├── api/            # API Gateway integration code
│   └── database/       # Database access code
├── tests/              # Test files
├── scripts/            # Deployment and utility scripts
└── docs/              # Documentation
```

## Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.8 or later
- Node.js and npm (for deployment tools)

## Deployment

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Deploy using AWS SAM:
```bash
sam build
sam deploy --guided
```

## License

MIT License - see LICENSE file for details
