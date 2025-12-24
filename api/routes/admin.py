import datetime
import os
import subprocess

from db.database import get_database
from db.db_core import Database
from dependencies.auth import require_authentication
from fastapi import APIRouter, Depends, HTTPException
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse

router = APIRouter(prefix="/admin", tags=["admin"])


class CleanupFileResponse(FileResponse):
    """Custom FileResponse that cleans up the file after sending"""

    def __init__(self, *args, cleanup_path: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup_path = cleanup_path

    async def __call__(self, scope, receive, send):
        """Send the file and then clean it up"""
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Clean up the file after it's been sent
            if self.cleanup_path and os.path.exists(self.cleanup_path):
                try:
                    os.unlink(self.cleanup_path)
                except Exception:
                    # Ignore cleanup errors
                    pass


@router.get("/database/download")
async def download_database(
    background_tasks: BackgroundTasks,
    user_info=Depends(require_authentication),
    db: Database = Depends(get_database),
):
    """
    Download a backup copy of the PostgreSQL database.
    Uses pg_dump for a consistent snapshot.
    Requires authentication.
    """
    try:
        # Generate backup filename
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d_%H-%M-%S"
        )
        backup_filename = f"backup-{timestamp}.sql"
        temp_backup_path = f"/tmp/{backup_filename}"

        try:
            # Get connection parameters from database instance
            conn_params = db.conn_params

            # Set PGPASSWORD environment variable for pg_dump
            env = os.environ.copy()
            env['PGPASSWORD'] = conn_params.get('password', '')

            # Run pg_dump to create backup
            result = subprocess.run(
                [
                    'pg_dump',
                    '-h', conn_params.get('host', 'localhost'),
                    '-p', str(conn_params.get('port', '5432')),
                    '-U', conn_params.get('user', 'cocktaildb'),
                    '-d', conn_params.get('dbname', 'cocktaildb'),
                    '-f', temp_backup_path,
                    '--no-owner',
                    '--no-acl',
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                raise Exception(f"pg_dump failed: {result.stderr}")

            # Return the file as a download with automatic cleanup after sending
            return CleanupFileResponse(
                path=temp_backup_path,
                media_type="application/sql",
                filename=backup_filename,
                cleanup_path=temp_backup_path,
            )

        except subprocess.TimeoutExpired:
            if os.path.exists(temp_backup_path):
                os.unlink(temp_backup_path)
            raise Exception("Database backup timed out")

        except Exception:
            # Clean up temp file only if backup failed
            if os.path.exists(temp_backup_path):
                os.unlink(temp_backup_path)
            raise

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error creating database backup: {str(e)}"
        )
