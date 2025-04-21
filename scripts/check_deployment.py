#!/usr/bin/env python3
import boto3
import json
import argparse
import sys
from datetime import datetime
import time


def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import boto3

        print("✓ Required dependencies are installed")
    except ImportError:
        print("Installing required dependencies...")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "boto3"])
        print("✓ Dependencies installed successfully")
        # Re-import after installation
        import boto3


def format_time(timestamp):
    """Format a timestamp into a readable string"""
    if isinstance(timestamp, datetime):
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    return str(timestamp)


def get_stack_events(cf_client, stack_name, max_events=10):
    """Get the most recent events for a stack"""
    try:
        response = cf_client.describe_stack_events(StackName=stack_name)
        events = response["StackEvents"][:max_events]

        print(f"\nMost recent stack events (max {max_events}):")
        print("-" * 100)
        print(
            f"{'Timestamp':<20} | {'Resource Type':<30} | {'Status':<25} | {'Reason'}"
        )
        print("-" * 100)

        for event in events:
            timestamp = format_time(event["Timestamp"])
            resource_type = event["ResourceType"]
            status = event["ResourceStatus"]
            reason = event.get("ResourceStatusReason", "N/A")

            print(f"{timestamp:<20} | {resource_type:<30} | {status:<25} | {reason}")

    except Exception as e:
        print(f"Error retrieving stack events: {str(e)}")


def get_stack_resources(cf_client, stack_name):
    """Get all resources in a stack"""
    try:
        response = cf_client.list_stack_resources(StackName=stack_name)
        resources = response["StackResourceSummaries"]

        print(f"\nStack resources:")
        print("-" * 100)
        print(
            f"{'Logical ID':<30} | {'Resource Type':<40} | {'Status':<20} | {'Physical ID'}"
        )
        print("-" * 100)

        for resource in resources:
            logical_id = resource["LogicalResourceId"]
            resource_type = resource["ResourceType"]
            status = resource["ResourceStatus"]
            physical_id = resource.get("PhysicalResourceId", "N/A")

            print(
                f"{logical_id:<30} | {resource_type:<40} | {status:<20} | {physical_id}"
            )

    except Exception as e:
        print(f"Error retrieving stack resources: {str(e)}")


def get_stack_outputs(cf_client, stack_name):
    """Get stack outputs"""
    try:
        response = cf_client.describe_stacks(StackName=stack_name)
        outputs = response["Stacks"][0].get("Outputs", [])

        if outputs:
            print(f"\nStack outputs:")
            print("-" * 100)
            print(f"{'Output Key':<30} | {'Output Value':<50} | {'Description'}")
            print("-" * 100)

            for output in outputs:
                key = output["OutputKey"]
                value = output["OutputValue"]
                description = output.get("Description", "N/A")

                print(f"{key:<30} | {value:<50} | {description}")
        else:
            print("\nNo outputs found for this stack.")

    except Exception as e:
        print(f"Error retrieving stack outputs: {str(e)}")


def check_api_gateway(apigw_client, stack_name):
    """Check API Gateway deployments and stages"""
    try:
        # List all APIs and filter by stack name
        apis = apigw_client.get_rest_apis()["items"]
        stack_apis = [api for api in apis if stack_name.lower() in api["name"].lower()]

        if not stack_apis:
            print("\nNo API Gateway APIs found for this stack.")
            return

        print(f"\nAPI Gateway APIs ({len(stack_apis)}):")
        print("-" * 100)
        print(f"{'API Name':<30} | {'API ID':<15} | {'Endpoint URL':<50}")
        print("-" * 100)

        for api in stack_apis:
            api_id = api["id"]
            api_name = api["name"]

            # Get stages for this API
            stages = apigw_client.get_stages(restApiId=api_id)["item"]

            for stage in stages:
                stage_name = stage["stageName"]
                endpoint_url = (
                    f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage_name}"
                )

                print(f"{api_name:<30} | {api_id:<15} | {endpoint_url:<50}")

    except Exception as e:
        print(f"Error checking API Gateway: {str(e)}")


def check_lambda_functions(lambda_client, stack_name):
    """Check Lambda functions in the stack"""
    try:
        # List all functions and filter by stack name
        response = lambda_client.list_functions()
        functions = response["Functions"]
        stack_functions = [
            fn for fn in functions if stack_name.lower() in fn["FunctionName"].lower()
        ]

        if not stack_functions:
            print("\nNo Lambda functions found for this stack.")
            return

        print(f"\nLambda Functions ({len(stack_functions)}):")
        print("-" * 100)
        print(
            f"{'Function Name':<40} | {'Runtime':<15} | {'Memory':<10} | {'Timeout':<10} | {'Last Modified'}"
        )
        print("-" * 100)

        for fn in stack_functions:
            name = fn["FunctionName"]
            runtime = fn["Runtime"]
            memory = fn["MemorySize"]
            timeout = fn["Timeout"]
            last_modified = fn["LastModified"]

            print(
                f"{name:<40} | {runtime:<15} | {memory:<10} | {timeout:<10} | {last_modified}"
            )

    except Exception as e:
        print(f"Error checking Lambda functions: {str(e)}")


def check_cloudfront(cf_client, stack_name):
    """Check CloudFront distributions"""
    try:
        # List all distributions
        response = cf_client.list_distributions()
        distributions = response["DistributionList"].get("Items", [])

        # Filter by tag (not reliable) or by domain name containing stack name
        stack_distributions = []
        for dist in distributions:
            # Try to get distribution tags
            dist_id = dist["Id"]

            # Check domain name for stack name
            if stack_name.lower() in dist["DomainName"].lower():
                stack_distributions.append(dist)
                continue

            # Check aliases
            aliases = dist.get("Aliases", {}).get("Items", [])
            if any(stack_name.lower() in alias.lower() for alias in aliases):
                stack_distributions.append(dist)
                continue

            # Check origins
            origins = dist.get("Origins", {}).get("Items", [])
            if any(
                stack_name.lower() in origin.get("DomainName", "").lower()
                for origin in origins
            ):
                stack_distributions.append(dist)

        if not stack_distributions:
            print("\nNo CloudFront distributions found for this stack.")
            return

        print(f"\nCloudFront Distributions ({len(stack_distributions)}):")
        print("-" * 100)
        print(
            f"{'Distribution ID':<20} | {'Domain Name':<40} | {'Status':<15} | {'Enabled'}"
        )
        print("-" * 100)

        for dist in stack_distributions:
            dist_id = dist["Id"]
            domain_name = dist["DomainName"]
            status = dist["Status"]
            enabled = "Yes" if dist["Enabled"] else "No"

            print(f"{dist_id:<20} | {domain_name:<40} | {status:<15} | {enabled}")

    except Exception as e:
        print(f"Error checking CloudFront distributions: {str(e)}")


def check_rds(rds_client, stack_name):
    """Check RDS instances and clusters"""
    try:
        # Check Aurora clusters
        clusters = rds_client.describe_db_clusters()["DBClusters"]
        stack_clusters = [
            c
            for c in clusters
            if stack_name.lower() in c["DBClusterIdentifier"].lower()
        ]

        # Check DB instances
        instances = rds_client.describe_db_instances()["DBInstances"]
        stack_instances = [
            i
            for i in instances
            if stack_name.lower() in i["DBInstanceIdentifier"].lower()
        ]

        # Check for serverless v2 instances related to our clusters
        for cluster in stack_clusters:
            cluster_id = cluster["DBClusterIdentifier"]
            related_instances = [
                i for i in instances if i.get("DBClusterIdentifier") == cluster_id
            ]
            for instance in related_instances:
                if instance not in stack_instances:
                    stack_instances.append(instance)

        if not stack_clusters and not stack_instances:
            print("\nNo RDS resources found for this stack.")
            return

        if stack_clusters:
            print(f"\nRDS Aurora Clusters ({len(stack_clusters)}):")
            print("-" * 100)
            print(
                f"{'Cluster ID':<30} | {'Status':<15} | {'Engine':<20} | {'Endpoint'}"
            )
            print("-" * 100)

            for cluster in stack_clusters:
                cluster_id = cluster["DBClusterIdentifier"]
                status = cluster["Status"]
                engine = f"{cluster['Engine']} {cluster.get('EngineVersion', '')}"
                endpoint = cluster["Endpoint"]

                print(f"{cluster_id:<30} | {status:<15} | {engine:<20} | {endpoint}")

        if stack_instances:
            print(f"\nRDS Instances ({len(stack_instances)}):")
            print("-" * 100)
            print(
                f"{'Instance ID':<30} | {'Status':<15} | {'Class':<20} | {'Endpoint'}"
            )
            print("-" * 100)

            for instance in stack_instances:
                instance_id = instance["DBInstanceIdentifier"]
                status = instance["DBInstanceStatus"]
                instance_class = instance["DBInstanceClass"]
                endpoint = instance.get("Endpoint", {}).get("Address", "N/A")

                print(
                    f"{instance_id:<30} | {status:<15} | {instance_class:<20} | {endpoint}"
                )

    except Exception as e:
        print(f"Error checking RDS resources: {str(e)}")


def main():
    parser = argparse.ArgumentParser(
        description="Check CloudFormation stack and diagnose issues"
    )
    parser.add_argument("--stack-name", "-s", help="CloudFormation stack name")
    parser.add_argument(
        "--region", "-r", default="us-east-1", help="AWS region (default: us-east-1)"
    )
    parser.add_argument("--profile", "-p", help="AWS CLI profile name")

    args = parser.parse_args()

    # Check if boto3 is installed
    check_dependencies()

    # Get stack name interactively if not provided
    stack_name = args.stack_name
    if not stack_name:
        stack_name = input("\nEnter your CloudFormation stack name: ").strip()
        if not stack_name:
            print("Error: No stack name provided. Exiting.")
            sys.exit(1)

    # Get region interactively if not provided
    global region
    region = args.region
    if not args.region:
        region = (
            input(f"\nEnter AWS region (default: us-east-1): ").strip() or "us-east-1"
        )

    # Create session
    session_kwargs = {"region_name": region}
    if args.profile:
        session_kwargs["profile_name"] = args.profile

    try:
        session = boto3.Session(**session_kwargs)
    except Exception as e:
        print(f"Error creating AWS session: {str(e)}")

        # Check if it's credentials issue and provide guidance
        if "credentials" in str(e).lower():
            print("\nThis may be an AWS credentials issue. Please ensure you have:")
            print("1. AWS CLI installed and configured")
            print("2. Valid credentials in ~/.aws/credentials or environment variables")
            print("3. Permission to access CloudFormation and related services")

        sys.exit(1)

    # Create service clients
    cf_client = session.client("cloudformation")
    apigw_client = session.client("apigateway")
    lambda_client = session.client("lambda")
    cloudfront_client = session.client("cloudfront")
    rds_client = session.client("rds")

    # Print header
    print(f"\n{'='*40}")
    print(f"Checking stack: {stack_name} in {region}")
    print(f"{'='*40}")

    # Check if stack exists
    try:
        stack_response = cf_client.describe_stacks(StackName=stack_name)
        stack = stack_response["Stacks"][0]

        # Print stack info
        print(f"\nStack Information:")
        print(f"Name: {stack['StackName']}")
        print(f"Status: {stack['StackStatus']}")
        print(f"Creation Time: {format_time(stack['CreationTime'])}")
        if "LastUpdatedTime" in stack:
            print(f"Last Updated: {format_time(stack['LastUpdatedTime'])}")

        # Get stack events
        get_stack_events(cf_client, stack_name)

        # Get stack resources
        get_stack_resources(cf_client, stack_name)

        # Get stack outputs
        get_stack_outputs(cf_client, stack_name)

        # Check API Gateway
        check_api_gateway(apigw_client, stack_name)

        # Check Lambda functions
        check_lambda_functions(lambda_client, stack_name)

        # Check CloudFront
        check_cloudfront(cloudfront_client, stack_name)

        # Check RDS
        check_rds(rds_client, stack_name)

    except Exception as e:
        error_message = str(e)
        print(f"Error: {error_message}")

        if "does not exist" in error_message:
            print(f"\nStack '{stack_name}' does not exist in region {region}.")
            print("Please check the stack name and region.")

        elif "ValidationError" in error_message:
            print(
                "\nValidation error - this could be due to incorrect stack name or insufficient permissions."
            )

        else:
            print(
                "\nAn unexpected error occurred. Please check your AWS credentials and permissions."
            )

    print("\nDiagnostics complete.")
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
