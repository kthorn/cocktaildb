import os
import json
import logging
import urllib.request
import sqlite3

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
            schema_file_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            db_name = event["ResourceProperties"].get("DBName", "cocktaildb")
            db_path = f"/mnt/efs/{db_name}.db"

            # Read schema from the provided file path
            schema_content = ""
            try:
                # Check if file exists in Lambda package
                if os.path.exists(schema_file_path):
                    with open(schema_file_path, "r") as f:
                        schema_content = f.read()
                    logger.info(f"Successfully read schema from {schema_file_path}")
            except Exception as e:
                logger.error(f"Error reading schema file: {str(e)}")
                raise ValueError(
                    f"Could not read schema from {schema_file_path}: {str(e)}"
                )

            if not schema_content:
                raise ValueError(f"No schema content found in {schema_file_path}")

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
                # If database exists and this is an update, delete it first
                if os.path.exists(db_path) and event["RequestType"] == "Update":
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
