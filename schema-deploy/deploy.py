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
    Supports both CloudFormation custom resource events and direct invocation
    """
    logger.info(f"Event: {json.dumps(event)}")

    # Check if this is a CloudFormation custom resource event
    is_cloudformation_event = "RequestType" in event and "StackId" in event
    
    try:
        # For CloudFormation events, only process Create/Update
        # For direct invocation, always process
        should_process = (
            not is_cloudformation_event or 
            event["RequestType"] in ["Create", "Update"]
        )
        
        if should_process:
            schema_content = ""
            
            # Handle both CloudFormation and direct invocation
            if is_cloudformation_event:
                properties = event["ResourceProperties"]
            else:
                properties = event  # For direct invocation, use event directly
                logger.info("Direct invocation detected - using event as properties")
            
            db_name = properties.get("DBName", "cocktaildb")
            db_path = f"/mnt/efs/{db_name}.db"
            
            # Check if this is a restore operation
            restore_from_s3 = properties.get("RestoreFromS3", "false").lower() == "true"
            restore_from_data = "BackupData" in properties
            
            if restore_from_s3:
                # Handle database restoration from S3 backup
                backup_bucket = properties.get("BackupS3Bucket")
                backup_key = properties.get("BackupS3Key")
                
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
                        
            elif restore_from_data:
                # Handle database restoration from direct backup data
                logger.info("Restoring database from provided backup data")
                
                try:
                    import base64
                    
                    # Get base64-encoded backup data
                    backup_data_b64 = properties.get("BackupData")
                    if not backup_data_b64:
                        raise ValueError("BackupData is required for data restoration")
                    
                    # Decode the backup data
                    backup_data = base64.b64decode(backup_data_b64)
                    
                    # Write directly to the database path
                    with open(db_path, 'wb') as f:
                        f.write(backup_data)
                        
                    logger.info(f"Successfully restored database to {db_path} from backup data")
                    logger.info(f"Restored database size: {len(backup_data)} bytes")
                    
                except Exception as e:
                    error_msg = f"Could not restore from backup data: {str(e)}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
            else:
                # Normal schema deployment
                # Try to get schema from direct input
                if "SchemaContent" in properties:
                    schema_content = properties["SchemaContent"]
                    logger.info("Successfully read schema from direct input SchemaContent")
                # Try to get schema from S3
                elif (
                    "SchemaS3Bucket" in properties
                    and "SchemaS3Key" in properties
                ):
                    s3_bucket = properties["SchemaS3Bucket"]
                    s3_key = properties["SchemaS3Key"]
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

                # Check if we should reinitialize the database completely
                force_init = (
                    properties.get("ForceInit", "false").lower() == "true"
                )
                
                # For Create operations or ForceInit, remove existing database and recreate
                if event["RequestType"] == "Create" or force_init:
                    if os.path.exists(db_path):
                        try:
                            os.remove(db_path)
                            logger.info(f"Removed existing database at {db_path}")
                        except Exception as e:
                            logger.warning(f"Failed to remove existing database: {str(e)}")

                    # Create and initialize the database
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.executescript(schema_content)
                    conn.commit()
                    conn.close()
                    logger.info(f"Successfully initialized database at {db_path}")
                
                # For Update operations without ForceInit, apply migration to existing database
                elif event["RequestType"] == "Update":
                    if not os.path.exists(db_path):
                        logger.warning(f"Database does not exist at {db_path}, creating new database")
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        cursor.executescript(schema_content)
                        conn.commit()
                        conn.close()
                        logger.info(f"Successfully created database at {db_path}")
                    else:
                        logger.info(f"Applying migration to existing database at {db_path}")
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        cursor.executescript(schema_content)
                        conn.commit()
                        conn.close()
                        logger.info(f"Successfully applied migration to database at {db_path}")

        # Send CloudFormation response only for CloudFormation events
        if is_cloudformation_event:
            send_response(
                event,
                context,
                "SUCCESS",
                {
                    "Message": "Schema file and database initialization completed successfully"
                },
            )
        else:
            logger.info("Direct invocation completed successfully")
            return {"statusCode": 200, "body": "Schema deployment completed successfully"}
    except Exception as e:
        error_msg = f"Error processing schema file or initializing database: {str(e)}"
        logger.error(error_msg)
        
        if is_cloudformation_event:
            send_response(event, context, "FAILED", {"Message": error_msg})
        else:
            logger.error("Direct invocation failed")
            return {"statusCode": 500, "body": f"Schema deployment failed: {error_msg}"}
