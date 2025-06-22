import datetime
import os
import sqlite3

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
    Download a backup copy of the SQLite database.
    Uses SQLite's backup API for a consistent snapshot.
    Requires authentication.
    """
    try:
        # Create a temporary file for the backup
        # Generate backup filename
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d_%H-%M-%S"
        )
        backup_filename = f"backup-{timestamp}.db"
        temp_backup_path = f"/tmp/{backup_filename}"  # Use Lambda's /tmp space

        try:
            source_db_path = db.db_path
            source_conn = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
            backup_conn = sqlite3.connect(temp_backup_path)

            try:
                # Perform the backup using SQLite's backup API
                source_conn.backup(backup_conn)

            finally:
                source_conn.close()
                backup_conn.close()

            # Return the file as a download with automatic cleanup after sending
            return CleanupFileResponse(
                path=temp_backup_path,
                media_type="application/octet-stream",
                filename=backup_filename,
                cleanup_path=temp_backup_path,
            )

        except Exception:
            # Clean up temp file only if backup failed
            if os.path.exists(temp_backup_path):
                os.unlink(temp_backup_path)
            raise

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error creating database backup: {str(e)}"
        )
