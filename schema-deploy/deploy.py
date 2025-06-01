import os
import json
import logging
import urllib.request
import sqlite3
import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


# CloudFormation response function
def send_response(event, context, response_status, response_data):
    response_body = {
        "Status": response_status,
        "Reason": "See the details in CloudWatch Log Stream: "
        + context.log_stream_name,
        "PhysicalResourceId": context.log_stream_name,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": response_data,
    }

    response_body_json = json.dumps(response_body)
    logger.info(f"Response body: {response_body_json}")

    headers = {"Content-Type": "", "Content-Length": str(len(response_body_json))}

    try:
        req = urllib.request.Request(
            url=event["ResponseURL"],
            data=response_body_json.encode("utf-8"),
            method="PUT",
            headers=headers,
        )
        with urllib.request.urlopen(req) as response:
            logger.info(f"Status code: {response.getcode()}")
            logger.info(f"Response: {response.read().decode('utf-8')}")
    except Exception as e:
        logger.error(f"Error sending response: {str(e)}")


def lambda_handler(event, context):
    """
    Custom resource handler to deploy the schema.sql file to EFS and initialize the database
    """
    logger.info(f"Event: {json.dumps(event)}")

    try:
        # Only process Create/Update events
        if event["RequestType"] in ["Create", "Update"]:
            schema_content = ""
            db_name = event["ResourceProperties"].get("DBName", "cocktaildb")
            db_path = f"/mnt/efs/{db_name}.db"
            
            # Check if this is a restore operation
            restore_from_s3 = event["ResourceProperties"].get("RestoreFromS3", "false").lower() == "true"
            
            if restore_from_s3:
                # Handle database restoration from S3 backup
                backup_bucket = event["ResourceProperties"].get("BackupS3Bucket")
                backup_key = event["ResourceProperties"].get("BackupS3Key")
                
                if not backup_bucket or not backup_key:
                    raise ValueError("BackupS3Bucket and BackupS3Key are required for restoration")
                
                logger.info(f"Restoring database from s3://{backup_bucket}/{backup_key}")
                
                # Download backup from S3
                temp_backup_path = f"/tmp/{backup_key}"
                try:
                    s3 = boto3.client("s3")
                    s3.download_file(backup_bucket, backup_key, temp_backup_path)
                    logger.info(f"Downloaded backup to {temp_backup_path}")
                except Exception as e:
                    logger.error(f"Error downloading backup from S3: {str(e)}")
                    raise ValueError(f"Could not download backup from s3://{backup_bucket}/{backup_key}: {str(e)}")
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                
                # Remove existing database if it exists
                if os.path.exists(db_path):
                    try:
                        os.remove(db_path)
                        logger.info(f"Removed existing database at {db_path}")
                    except Exception as e:
                        logger.warning(f"Failed to remove existing database: {str(e)}")
                
                # Copy the backup to the target location
                try:
                    import shutil
                    shutil.copy2(temp_backup_path, db_path)
                    logger.info(f"Restored database from backup to {db_path}")
                    
                    # Verify the restored database
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    table_count = cursor.fetchone()[0]
                    conn.close()
                    logger.info(f"Restored database contains {table_count} tables")
                    
                except Exception as e:
                    logger.error(f"Error restoring database: {str(e)}")
                    raise ValueError(f"Could not restore database: {str(e)}")
                finally:
                    # Clean up temporary file
                    if os.path.exists(temp_backup_path):
                        try:
                            os.remove(temp_backup_path)
                            logger.info(f"Cleaned up temporary backup file: {temp_backup_path}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up temporary file: {str(e)}")
                
            else:
                # Normal schema deployment
                # Try to get schema from direct input
                if "SchemaContent" in event["ResourceProperties"]:
                    schema_content = event["ResourceProperties"]["SchemaContent"]
                    logger.info("Successfully read schema from direct input SchemaContent")
                # Try to get schema from S3
                elif (
                    "SchemaS3Bucket" in event["ResourceProperties"]
                    and "SchemaS3Key" in event["ResourceProperties"]
                ):
                    s3_bucket = event["ResourceProperties"]["SchemaS3Bucket"]
                    s3_key = event["ResourceProperties"]["SchemaS3Key"]
                    logger.info(
                        f"Attempting to download schema from S3: s3://{s3_bucket}/{s3_key}"
                    )
                    try:
                        s3 = boto3.client("s3")
                        response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
                        schema_content = response["Body"].read().decode("utf-8")
                        logger.info(
                            f"Successfully downloaded schema from S3: s3://{s3_bucket}/{s3_key}"
                        )
                    except Exception as e:
                        logger.error(f"Error downloading schema from S3: {str(e)}")
                        raise ValueError(
                            f"Could not download schema from s3://{s3_bucket}/{s3_key}: {str(e)}"
                        )
                # Fallback to local file
                else:
                    schema_file_path = os.path.join(os.path.dirname(__file__), "schema.sql")
                    try:
                        # Check if file exists in Lambda package
                        if os.path.exists(schema_file_path):
                            with open(schema_file_path, "r") as f:
                                schema_content = f.read()
                            logger.info(f"Successfully read schema from {schema_file_path}")
                    except Exception as e:
                        logger.error(f"Error reading schema file: {str(e)}")
                        # Raise error only if this is the fallback and it fails
                        raise ValueError(
                            f"Could not read schema from {schema_file_path}: {str(e)}"
                        )

                if not schema_content:
                    raise ValueError(
                        "No schema content found from any source (Direct, S3, or local file)"
                    )

                # Ensure directory exists
                os.makedirs(os.path.dirname(db_path), exist_ok=True)

                # Initialize the database
                logger.info(f"Initializing database at {db_path}")

                # For updates, only reinitialize if forced
                force_init = (
                    event["ResourceProperties"].get("ForceInit", "false").lower() == "true"
                )
                if (
                    event["RequestType"] == "Update"
                    and os.path.exists(db_path)
                    and not force_init
                ):
                    logger.info(
                        f"Database already exists at {db_path}. Not reinitializing."
                    )
                else:
                    # If database exists and this is a Create, delete it first
                    if os.path.exists(db_path) and event["RequestType"] in ["Create"]:
                        try:
                            os.remove(db_path)
                            logger.info(f"Removed existing database at {db_path}")
                        except Exception as e:
                            logger.warning(f"Failed to remove existing database: {str(e)}")

                    # Create and initialize the database
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    # Execute the schema SQL
                    cursor.executescript(schema_content)
                    # Commit changes and close connection
                    conn.commit()
                    conn.close()
                    logger.info(f"Successfully initialized database at {db_path}")

        # Always return success for Delete events
        send_response(
            event,
            context,
            "SUCCESS",
            {
                "Message": "Schema file and database initialization completed successfully"
            },
        )
    except Exception as e:
        error_msg = f"Error processing schema file or initializing database: {str(e)}"
        logger.error(error_msg)
        send_response(event, context, "FAILED", {"Message": error_msg})
