#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL.
Downloads SQLite backup from S3, transforms data, and inserts into PostgreSQL.

Usage:
    # From local SQLite file:
    python migrate-sqlite-to-postgres.py --sqlite /path/to/db.sqlite --pg-password secret

    # From S3 backup:
    python migrate-sqlite-to-postgres.py --s3-bucket cocktaildbbackups-xxx --pg-password secret
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

import boto3
import psycopg2
from psycopg2.extras import execute_values

# Tables in dependency order (parent tables first)
TABLES = [
    'units',
    'ingredients',
    'recipes',
    'recipe_ingredients',
    'ratings',
    'tags',
    'recipe_tags',
    'user_ingredients',
]


def download_latest_backup(bucket: str, local_path: str) -> str:
    """Download latest backup from S3."""
    s3 = boto3.client('s3')

    # List backups and get latest
    response = s3.list_objects_v2(Bucket=bucket, Prefix='backup-')
    if 'Contents' not in response:
        raise ValueError(f"No backups found in bucket {bucket}")

    latest = max(response['Contents'], key=lambda x: x['LastModified'])
    key = latest['Key']

    print(f"Downloading {key} from s3://{bucket}/")
    s3.download_file(bucket, key, local_path)
    return local_path


def get_sqlite_data(sqlite_path: str, table: str) -> tuple:
    """Extract all data from a SQLite table."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return [], []

    columns = list(rows[0].keys())
    data = [tuple(row) for row in rows]

    conn.close()
    return columns, data


def insert_postgres_data(pg_conn, table: str, columns: list, data: list):
    """Insert data into PostgreSQL table."""
    if not data:
        print(f"  No data to insert for {table}")
        return

    cursor = pg_conn.cursor()

    # Disable triggers during import for performance
    cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER ALL")

    # Build INSERT statement
    cols_str = ', '.join(columns)

    # Use execute_values for bulk insert with ON CONFLICT DO NOTHING
    insert_sql = f"INSERT INTO {table} ({cols_str}) VALUES %s ON CONFLICT DO NOTHING"

    execute_values(cursor, insert_sql, data, page_size=1000)

    # Re-enable triggers
    cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER ALL")

    # Reset sequence to max id + 1
    if 'id' in columns:
        cursor.execute(f"""
            SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                          COALESCE((SELECT MAX(id) FROM {table}), 1))
        """)

    pg_conn.commit()
    print(f"  Inserted {len(data)} rows into {table}")


def apply_schema(pg_conn, schema_path: str):
    """Apply PostgreSQL schema from file."""
    print(f"Applying schema from {schema_path}")

    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    cursor = pg_conn.cursor()
    cursor.execute(schema_sql)
    pg_conn.commit()
    print("  Schema applied successfully")


def migrate(sqlite_path: str, pg_conn_str: str, schema_path: str = None):
    """Migrate all data from SQLite to PostgreSQL."""
    pg_conn = psycopg2.connect(pg_conn_str)

    # Apply schema if provided
    if schema_path and os.path.exists(schema_path):
        apply_schema(pg_conn, schema_path)

    # Migrate each table
    for table in TABLES:
        print(f"Migrating {table}...")
        columns, data = get_sqlite_data(sqlite_path, table)
        insert_postgres_data(pg_conn, table, columns, data)

    pg_conn.close()
    print("\nMigration complete!")


def main():
    parser = argparse.ArgumentParser(description='Migrate SQLite to PostgreSQL')
    parser.add_argument('--sqlite', help='Path to SQLite database')
    parser.add_argument('--s3-bucket', help='S3 bucket with backups')
    parser.add_argument('--schema', help='Path to PostgreSQL schema file',
                        default='infrastructure/postgres/schema.sql')
    parser.add_argument('--pg-host', default='localhost')
    parser.add_argument('--pg-port', default='5432')
    parser.add_argument('--pg-db', default='cocktaildb')
    parser.add_argument('--pg-user', default='cocktaildb')
    parser.add_argument('--pg-password', required=True)
    parser.add_argument('--skip-schema', action='store_true',
                        help='Skip applying schema (if already applied)')

    args = parser.parse_args()

    # Get SQLite database
    if args.sqlite:
        sqlite_path = args.sqlite
        if not os.path.exists(sqlite_path):
            print(f"Error: SQLite file not found: {sqlite_path}")
            sys.exit(1)
    elif args.s3_bucket:
        sqlite_path = '/tmp/cocktaildb_backup.db'
        download_latest_backup(args.s3_bucket, sqlite_path)
    else:
        print("Error: Must provide --sqlite or --s3-bucket")
        sys.exit(1)

    # Build PostgreSQL connection string
    pg_conn_str = (
        f"host={args.pg_host} "
        f"port={args.pg_port} "
        f"dbname={args.pg_db} "
        f"user={args.pg_user} "
        f"password={args.pg_password}"
    )

    # Determine schema path
    schema_path = None if args.skip_schema else args.schema

    migrate(sqlite_path, pg_conn_str, schema_path)


if __name__ == '__main__':
    main()
