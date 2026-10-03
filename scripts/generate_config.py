#!/usr/bin/env python3
"""
Script to generate config.js for the Cocktail Database application.
Retrieves configuration values from CloudFormation outputs and generates the config.js file.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

PUBLIC_CONFIG_FIELDS = (
    "apiUrl",
    "userPoolId",
    "clientId",
    "cognitoDomain",
    "appUrl",
    "appName",
)
PUBLIC_URL_FIELDS = ("apiUrl", "cognitoDomain", "appUrl")


def get_cloudformation_output(stack_name, output_key, region="us-east-1"):
    """Get a specific output value from a CloudFormation stack."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as e:
        print(
            f"Error retrieving CloudFormation output {output_key}: "
            f"boto3/botocore is required for AWS lookup: {e}"
        )
        return None

    try:
        cf_client = boto3.client("cloudformation", region_name=region)
        response = cf_client.describe_stacks(StackName=stack_name)

        if not response["Stacks"]:
            print(f"Error: Stack {stack_name} not found")
            return None

        outputs = response["Stacks"][0].get("Outputs", [])
        for output in outputs:
            if output["OutputKey"] == output_key:
                return output["OutputValue"]

        print(f"Warning: Output key '{output_key}' not found in stack {stack_name}")
        return None

    except (BotoCoreError, ClientError, KeyError) as e:
        print(f"Error retrieving CloudFormation output {output_key}: {e}")
        return None


def render_public_config(config: dict) -> str:
    """Validate and serialize the browser-visible runtime configuration."""
    if not isinstance(config, dict):
        raise TypeError("public configuration must be a dictionary")

    missing = [field for field in PUBLIC_CONFIG_FIELDS if field not in config]
    if missing:
        raise ValueError(f"missing required public configuration fields: {missing}")

    unexpected = sorted(set(config) - set(PUBLIC_CONFIG_FIELDS))
    if unexpected:
        raise ValueError(f"unexpected public configuration fields: {unexpected}")

    for field in PUBLIC_CONFIG_FIELDS:
        value = config[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-blank string")

    for field in PUBLIC_URL_FIELDS:
        value = config[field]
        try:
            parsed = urlparse(value)
            has_supported_scheme = parsed.scheme in {"http", "https"}
            has_hostname = bool(parsed.hostname)
        except ValueError:
            has_supported_scheme = False
            has_hostname = False
        if not has_supported_scheme or not has_hostname:
            raise ValueError(f"{field} must use http or https and include a hostname")

    public_config = {field: config[field] for field in PUBLIC_CONFIG_FIELDS}
    return f"export default {json.dumps(public_config)};\n"


def get_app_url(stack_name, target_env, region):
    """Determine the correct App URL based on environment."""
    if target_env == "prod":
        # Try to get custom domain URL first
        custom_domain_url = get_cloudformation_output(
            stack_name, "CustomDomainURL", region
        )

        if custom_domain_url and custom_domain_url != "N/A (dev environment)":
            return custom_domain_url

        # Fall back to CloudFront URL for prod.
        return get_cloudformation_output(stack_name, "CloudFrontURL", region)

    # For dev, always use CloudFront URL.
    return get_cloudformation_output(stack_name, "CloudFrontURL", region)


def generate_config_js(config_values, target_env, output_path):
    """Generate the config.js file with the provided configuration values."""
    try:
        config = {
            "apiUrl": config_values["api_url"],
            "userPoolId": config_values["user_pool_id"],
            "clientId": config_values["client_id"],
            "cognitoDomain": config_values["cognito_domain"],
            "appUrl": config_values["app_url"],
            "appName": f"Cocktail Database ({target_env})",
        }
        config_content = render_public_config(config)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(config_content, encoding="utf-8")
        print(f"config.js updated successfully for {target_env}")
        return True
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as e:
        print(f"Error writing config.js: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate config.js for Cocktail Database application"
    )
    parser.add_argument("stack_name", help="CloudFormation stack name")
    parser.add_argument(
        "target_env", choices=["dev", "prod"], help="Target environment (dev or prod)"
    )
    parser.add_argument(
        "--region", default="us-east-1", help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--output",
        default="src/web/js/config.js",
        help="Output path for config.js (default: src/web/js/config.js)",
    )

    args = parser.parse_args()

    print(
        f"Generating config.js for stack: {args.stack_name}, environment: {args.target_env}"
    )

    # Get all required CloudFormation outputs
    config_values = {}

    # Get API endpoint
    config_values["api_url"] = get_cloudformation_output(
        args.stack_name, "ApiEndpoint", args.region
    )
    # Get Cognito configuration
    config_values["user_pool_id"] = get_cloudformation_output(
        args.stack_name, "UserPoolId", args.region
    )
    config_values["client_id"] = get_cloudformation_output(
        args.stack_name, "UserPoolClientId", args.region
    )
    config_values["cognito_domain"] = get_cloudformation_output(
        args.stack_name, "CognitoDomainURLV3", args.region
    )
    # Get App URL
    config_values["app_url"] = get_app_url(
        args.stack_name, args.target_env, args.region
    )
    # Check if we have all required values
    missing_values = [key for key, value in config_values.items() if not value]
    if missing_values:
        print(f"Error: Missing required configuration values: {missing_values}")
        print("Skipping config.js update due to missing values.")
        sys.exit(1)

    # Generate config.js
    success = generate_config_js(config_values, args.target_env, args.output)

    if not success:
        sys.exit(1)

    print("Configuration generation completed successfully!")


if __name__ == "__main__":
    main()
