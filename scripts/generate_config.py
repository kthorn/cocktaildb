#!/usr/bin/env python3
"""
Script to generate config.js for the Cocktail Database application.
Retrieves configuration values from CloudFormation outputs and generates the config.js file.
"""

import argparse
import boto3
import sys
import os
from pathlib import Path


def get_cloudformation_output(stack_name, output_key, region="us-east-1"):
    """Get a specific output value from a CloudFormation stack."""
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

    except Exception as e:
        print(f"Error retrieving CloudFormation output {output_key}: {e}")
        return None


def has_problematic_characters(value):
    """Check if a value contains problematic characters like parentheses."""
    if not value:
        return False
    return "(" in value or ")" in value


def get_app_url(stack_name, target_env, region):
    """Determine the correct App URL based on environment."""
    if target_env == "prod":
        # Try to get custom domain URL first
        custom_domain_url = get_cloudformation_output(
            stack_name, "CustomDomainURL", region
        )

        if (
            custom_domain_url
            and custom_domain_url != "N/A (dev environment)"
            and not has_problematic_characters(custom_domain_url)
        ):
            return custom_domain_url
        else:
            # Fall back to CloudFront URL for prod
            cloudfront_url = get_cloudformation_output(
                stack_name, "CloudFrontURL", region
            )
            if has_problematic_characters(cloudfront_url):
                print(
                    f"WARNING: CloudFrontURL contains problematic characters: {cloudfront_url}"
                )
                return None
            return cloudfront_url
    else:
        # For dev, always use CloudFront URL
        cloudfront_url = get_cloudformation_output(stack_name, "CloudFrontURL", region)
        if has_problematic_characters(cloudfront_url):
            print(
                f"WARNING: CloudFrontURL contains problematic characters: {cloudfront_url}"
            )
            return None
        return cloudfront_url


def validate_value(value, name):
    """Validate a configuration value and clear it if it has problematic characters."""
    if not value:
        return value

    if has_problematic_characters(value):
        print(
            f"WARNING: {name} contains parentheses, likely an error. Clearing {name}."
        )
        return None
    return value


def generate_config_js(config_values, target_env, output_path):
    """Generate the config.js file with the provided configuration values."""
    config_content = f"""// Configuration for the Cocktail Database application ({target_env} environment)
const config = {{
    // API endpoint
    apiUrl: '{config_values["api_url"]}',

    // Cognito configuration
    userPoolId: '{config_values["user_pool_id"]}',
    clientId: '{config_values["client_id"]}',
    cognitoDomain: '{config_values["cognito_domain"]}', // This is the base Cognito Hosted UI domain

    // Application URL (for redirects, etc.)
    appUrl: '{config_values["app_url"]}',

    // General settings
    appName: 'Cocktail Database ({target_env})'
}};

// Export the configuration
export default config;
"""

    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        print(f"config.js updated successfully for {target_env}")
        return True

    except Exception as e:
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
    config_values["api_url"] = validate_value(config_values["api_url"], "API_URL")

    # Get Cognito configuration
    config_values["user_pool_id"] = get_cloudformation_output(
        args.stack_name, "UserPoolId", args.region
    )
    config_values["user_pool_id"] = validate_value(
        config_values["user_pool_id"], "USER_POOL_ID"
    )

    config_values["client_id"] = get_cloudformation_output(
        args.stack_name, "UserPoolClientId", args.region
    )
    config_values["client_id"] = validate_value(config_values["client_id"], "CLIENT_ID")

    config_values["cognito_domain"] = get_cloudformation_output(
        args.stack_name, "CognitoDomainURL", args.region
    )
    config_values["cognito_domain"] = validate_value(
        config_values["cognito_domain"], "COGNITO_DOMAIN_OUTPUT_URL"
    )

    # Get App URL
    config_values["app_url"] = get_app_url(
        args.stack_name, args.target_env, args.region
    )
    config_values["app_url"] = validate_value(config_values["app_url"], "APP_URL")

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
