from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
import tempfile
import sqlite3
import os
from dependencies.auth import require_authentication
from db.database import get_database
from db.db_core import Database

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/database/download")
async def download_database(
    user_info=Depends(require_authentication), db: Database = Depends(get_database)
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

            # Use the database's connection method and SQLite's backup API
            # This works even while the database is being used
            source_conn = db._get_connection()
            backup_conn = sqlite3.connect(temp_db_path)

            try:
                # Perform the backup
                source_conn.backup(backup_conn)
            finally:
                source_conn.close()
                backup_conn.close()

            # Return the file as a download
            return FileResponse(
                path=temp_db_path,
                media_type="application/octet-stream",
                filename="cocktaildb_backup.db",
                background=None,  # Let FastAPI handle cleanup
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
