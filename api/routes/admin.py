from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks
import tempfile
import sqlite3
import os
from dependencies.auth import require_authentication
from db.database import get_database
from db.db_core import Database

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/database/download")
async def download_database(
    background_tasks: BackgroundTasks,
    user_info=Depends(require_authentication), 
    db: Database = Depends(get_database)
):
    """
    Download a backup copy of the SQLite database.
    Uses SQLite's backup API for a consistent snapshot.
    Requires authentication.
    """
    try:
        # Create a temporary file for the backup
        temp_fd, temp_db_path = tempfile.mkstemp(
            suffix=".db", prefix="cocktaildb_backup_"
        )

        try:
            # Close the file descriptor as we'll use SQLite to write to it
            os.close(temp_fd)

            # Get the source database path
            source_db_path = db.db_path
            
            # Connect directly to source and destination databases
            # Use a fresh connection without WAL mode for backup
            source_conn = sqlite3.connect(source_db_path, timeout=30.0)
            backup_conn = sqlite3.connect(temp_db_path)

            try:
                # Checkpoint WAL file first to ensure all data is in main db
                # Use TRUNCATE mode to ensure WAL is fully flushed
                source_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                
                # Perform the backup using SQLite's backup API
                source_conn.backup(backup_conn)
                
                # Ensure backup is fully written
                backup_conn.execute("PRAGMA integrity_check")
                
            finally:
                source_conn.close()
                backup_conn.close()

            # Schedule cleanup of the temporary file
            background_tasks.add_task(os.unlink, temp_db_path)
            
            # Return the file as a download
            return FileResponse(
                path=temp_db_path,
                media_type="application/octet-stream",
                filename="cocktaildb_backup.db",
            )

        except Exception:
            # Clean up temp file if backup failed
            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)
            raise

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error creating database backup: {str(e)}"
        )
