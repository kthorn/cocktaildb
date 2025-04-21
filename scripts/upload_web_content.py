#!/usr/bin/env python
import subprocess
import sys
import os
import json
import boto3
import mimetypes

# Change to project root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
os.chdir(project_root)
print(f"Changed directory to: {os.getcwd()}")

STACK_NAME = "cocktail-db-prod"


def run_command_with_output(command):
    """Run a command and return output"""
    print(f"Running: {command}")
    try:
        output = subprocess.check_output(
            command, shell=True, stderr=subprocess.STDOUT, text=True
        )
        return output
    except subprocess.CalledProcessError as e:
        if (
            e.returncode == 255
            and "Stack with id" in e.output
            and "does not exist" in e.output
        ):
            return None
        raise


def get_stack_outputs():
    """Get the outputs from the CloudFormation stack"""
    try:
        output = run_command_with_output(
            f"aws cloudformation describe-stacks --stack-name {STACK_NAME} --query 'Stacks[0].Outputs'"
        )
        if output:
            outputs = json.loads(output)
            result = {}
            for output in outputs:
                result[output["OutputKey"]] = output["OutputValue"]
            return result
        return None
    except Exception as e:
        print(f"Error getting stack outputs: {e}")
        return None


def upload_web_content():
    """Upload web content to S3"""
    try:
        # Get the website bucket name from stack outputs
        stack_outputs = get_stack_outputs()
        if not stack_outputs or "WebsiteURL" not in stack_outputs:
            print("WebsiteURL not found in stack outputs. Skipping web content upload.")
            return

        # Extract bucket name from the website URL
        website_url = stack_outputs["WebsiteURL"]
        # Format: http://bucket-name.s3-website-region.amazonaws.com
        bucket_name = website_url.split("//")[1].split(".")[0]
        api_endpoint = stack_outputs["ApiEndpoint"]

        print(f"Using website bucket: {bucket_name}")
        print(f"API Endpoint: {api_endpoint}")

        # Create S3 client
        s3 = boto3.client("s3")

        # Update api.js with the correct API endpoint
        web_dir = os.path.join(project_root, "src", "web")
        api_js_path = os.path.join(web_dir, "js", "api.js")

        # Read the api.js file
        with open(api_js_path, "r") as f:
            api_js_content = f.read()

        # Replace the localhost URL with the API Gateway URL
        updated_api_js = api_js_content.replace(
            "constructor(baseUrl = 'http://localhost:3000/api')",
            f"constructor(baseUrl = '{api_endpoint}')",
        )

        # Write the updated content back to the file
        with open(api_js_path, "w") as f:
            f.write(updated_api_js)

        print("Updated API endpoint in api.js")

        # Upload web content to S3
        for root, dirs, files in os.walk(web_dir):
            for file in files:
                local_path = os.path.join(root, file)
                # Get relative path from web_dir
                relative_path = os.path.relpath(local_path, web_dir)
                print(f"Uploading {relative_path} to S3")

                # Determine content type
                content_type = mimetypes.guess_type(local_path)[0]
                if content_type is None:
                    # Default content type
                    if file.endswith(".js"):
                        content_type = "application/javascript"
                    elif file.endswith(".css"):
                        content_type = "text/css"
                    elif file.endswith(".html"):
                        content_type = "text/html"
                    elif file.endswith(".json"):
                        content_type = "application/json"
                    else:
                        content_type = "binary/octet-stream"

                # Upload file with content type
                s3.upload_file(
                    local_path,
                    bucket_name,
                    relative_path,
                    ExtraArgs={"ContentType": content_type},
                )

        print("Web content uploaded successfully!")
        print(
            f"Your website is available at: {stack_outputs.get('CloudFrontURL', 'Unknown')}"
        )

    except Exception as e:
        print(f"Error uploading web content: {e}")


if __name__ == "__main__":
    upload_web_content()
