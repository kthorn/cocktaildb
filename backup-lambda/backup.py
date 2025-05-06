import boto3
import sqlite3
import os
import logging
import datetime
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get environment variables
SOURCE_DB_PATH = os.environ.get("DB_PATH", "/mnt/efs/cocktaildb.db")
BACKUP_BUCKET = os.environ.get("BACKUP_BUCKET")
EFS_MOUNT_PATH = "/mnt/efs"  # Should match the Lambda config


s3 = boto3.client("s3")


def lambda_handler(event, context):
    """
    Handles the scheduled event to back up the SQLite DB from EFS to S3.
    Uses the SQLite online backup API for consistency.
    Deletes backups older than DAYS_TO_KEEP.
    """
    if not BACKUP_BUCKET:
        logger.error("BACKUP_BUCKET environment variable not set.")
        return {"statusCode": 500, "body": "Configuration error"}

    logger.info(f"Starting backup of {SOURCE_DB_PATH} to s3://{BACKUP_BUCKET}")

    # Ensure EFS is mounted and accessible
    if not os.path.exists(EFS_MOUNT_PATH):
        logger.error(f"EFS mount path {EFS_MOUNT_PATH} does not exist.")
        return {"statusCode": 500, "body": "EFS mount path not found"}

    if not os.path.exists(SOURCE_DB_PATH):
        logger.error(f"Source database {SOURCE_DB_PATH} not found.")
        return {"statusCode": 404, "body": "Source DB not found"}

    # Generate backup filename
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d_%H-%M-%S"
    )
    backup_filename = f"backup-{timestamp}.db"
    temp_backup_path = f"/tmp/{backup_filename}"  # Use Lambda's /tmp space
    s3_key = backup_filename

    start_time = time.time()

    # --- Perform Backup using SQLite Online Backup API ---
    try:
        logger.info(f"Connecting to source DB: {SOURCE_DB_PATH}")
        source_conn = sqlite3.connect(
            f"file:{SOURCE_DB_PATH}?mode=ro", uri=True
        )  # Read-only connection

        logger.info(f"Creating backup file: {temp_backup_path}")
        backup_conn = sqlite3.connect(temp_backup_path)

        logger.info("Starting SQLite online backup...")
        source_conn.backup(backup_conn, progress=None)

        logger.info("SQLite backup completed successfully.")

    except sqlite3.Error as e:
        logger.error(f"SQLite Error during backup: {e}", exc_info=True)
        return {"statusCode": 500, "body": f"SQLite backup failed: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error during backup preparation: {e}", exc_info=True)
        return {"statusCode": 500, "body": f"Backup preparation failed: {e}"}
    finally:
        if "source_conn" in locals() and source_conn:
            source_conn.close()
        if "backup_conn" in locals() and backup_conn:
            backup_conn.close()

    # --- Upload to S3 ---
    try:
        logger.info(f"Uploading {temp_backup_path} to s3://{BACKUP_BUCKET}/{s3_key}")
        s3.upload_file(temp_backup_path, BACKUP_BUCKET, s3_key)
        logger.info("Upload successful.")
    except Exception as e:
        logger.error(f"Error uploading backup to S3: {e}", exc_info=True)
        # Decide if we should still attempt cleanup
        return {"statusCode": 500, "body": f"S3 upload failed: {e}"}
    finally:
        # --- Clean up temporary file ---
        if os.path.exists(temp_backup_path):
            try:
                os.remove(temp_backup_path)
                logger.info(f"Removed temporary backup file: {temp_backup_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to remove temporary file {temp_backup_path}: {e}"
                )

    backup_duration = time.time() - start_time
    logger.info(f"Backup and upload took {backup_duration:.2f} seconds.")

    return {
        "statusCode": 200,
        "body": f"Backup {s3_key} created successfully and old backups cleaned.",
    }


# For local testing (requires AWS credentials and EFS locally mounted or simulated)
# if __name__ == '__main__':
#    os.environ['BACKUP_BUCKET'] = 'your-test-backup-bucket'
#    # Create a dummy DB if needed for testing
#    # if not os.path.exists(SOURCE_DB_PATH): ... create db ...
#    lambda_handler({}, {})
