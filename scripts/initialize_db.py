import json
import os
import sys
import time
from botocore.exceptions import ClientError

import boto3
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Import the models and Base from the schema
from cocktaildb.schema import Base

# Initialize boto3 clients
secretsmanager = boto3.client("secretsmanager")
rds = boto3.client("rds")
rds_data = boto3.client("rds-data")


def get_db_connection_string():
    """Get database credentials from Secrets Manager and build connection string"""
    secret_arn = os.environ.get("DB_SECRET_ARN")
    print(f"Secret ARN: {secret_arn}")
    cluster_arn = os.environ.get("DB_CLUSTER_ARN")
    print(f"Cluster ARN: {cluster_arn}")
    db_name = os.environ.get("DB_NAME", "cocktaildb")
    print(f"Database Name: {db_name}")

    if not secret_arn or not cluster_arn:
        raise ValueError(
            "Environment variables DB_SECRET_ARN and DB_CLUSTER_ARN must be set"
        )

    # Get credentials from Secrets Manager
    response = secretsmanager.get_secret_value(SecretId=secret_arn)
    credentials = json.loads(response["SecretString"])

    # Get cluster endpoint
    cluster_info = rds.describe_db_clusters(
        DBClusterIdentifier=cluster_arn.split(":")[-1]
    )
    endpoint = cluster_info["DBClusters"][0]["Endpoint"]

    # Create PostgreSQL connection string using pg8000
    conn_string = f"postgresql+pg8000://{credentials['username']}:{credentials['password']}@{endpoint}:5432/{db_name}"
    return conn_string


def execute_sql_with_retry(sql, parameters=None, max_retries=5, initial_delay=1):
    """Execute SQL using RDS Data API with retry logic for database resuming"""
    secret_arn = os.environ.get("DB_SECRET_ARN")
    cluster_arn = os.environ.get("DB_CLUSTER_ARN")
    db_name = os.environ.get("DB_NAME", "cocktaildb")

    print(f"Executing SQL: {sql}")
    if parameters:
        print(f"With parameters: {parameters}")

    retry_count = 0
    delay = initial_delay

    while retry_count < max_retries:
        try:
            response = rds_data.execute_statement(
                resourceArn=cluster_arn,
                secretArn=secret_arn,
                database=db_name,
                sql=sql,
                parameters=parameters or [],
                continueAfterTimeout=True,
            )
            print(f"SQL execution successful. Response: {response}")
            return response
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "DatabaseResumingException":
                if retry_count < max_retries - 1:
                    print(f"Database is resuming. Retrying in {delay} seconds...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    retry_count += 1
                    continue
            print(f"Error executing SQL: {e}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error details: {str(e)}")
            raise
        except Exception as e:
            print(f"Error executing SQL: {e}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error details: {str(e)}")
            raise

    raise Exception(f"Failed to execute SQL after {max_retries} retries")


def initialize_database():
    """Create all tables and add default data"""
    try:
        # Drop all tables
        print("Dropping all existing tables...")
        print("Attempting to drop schema...")
        execute_sql_with_retry("DROP SCHEMA public CASCADE;")
        print("Schema dropped successfully")

        print("Creating new schema...")
        execute_sql_with_retry("CREATE SCHEMA public;")
        print("Schema created successfully")

        # Create tables
        print("Creating tables...")
        dialect = postgresql_dialect()
        for table in Base.metadata.tables.values():
            print(f"Creating table: {table.name}")
            print(f"Table columns: {[c.name for c in table.columns]}")
            print(f"Table constraints: {[c.name for c in table.constraints]}")

            # Generate CREATE TABLE SQL manually
            columns = []
            for column in table.columns:
                if column.primary_key:
                    col_def = f"{column.name} SERIAL PRIMARY KEY"
                else:
                    col_def = f"{column.name} {column.type}"
                    if not column.nullable:
                        col_def += " NOT NULL"
                columns.append(col_def)

            create_table_sql = f"CREATE TABLE {table.name} ({', '.join(columns)})"
            print(f"Table creation SQL: {create_table_sql}")
            execute_sql_with_retry(create_table_sql)
            print(f"Table {table.name} created successfully")

        # Add default data
        print("Starting to add default data...")
        add_default_data()

        print("Database initialization completed successfully!")

    except Exception as e:
        print(f"Error initializing database: {e}")
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {str(e)}")
        raise


def add_default_data():
    """Add default units and ingredients"""
    print("Adding default units...")
    default_units = [
        {"name": "Ounce", "abbreviation": "oz"},
        {"name": "Milliliter", "abbreviation": "ml"},
        {"name": "Teaspoon", "abbreviation": "tsp"},
        {"name": "Tablespoon", "abbreviation": "tbsp"},
        {"name": "Dash", "abbreviation": "dash"},
    ]

    for unit in default_units:
        execute_sql_with_retry(
            "INSERT INTO units (name, abbreviation) VALUES (:name, :abbreviation)",
            [
                {"name": "name", "value": {"stringValue": unit["name"]}},
                {
                    "name": "abbreviation",
                    "value": {"stringValue": unit["abbreviation"]},
                },
            ],
        )

    print("Adding default ingredients...")
    default_ingredients = [
        {"name": "Gin", "category": "Spirit"},
        {"name": "Vodka", "category": "Spirit"},
        {"name": "Rum", "category": "Spirit"},
        {"name": "Tequila", "category": "Spirit"},
        {"name": "Whiskey", "category": "Spirit"},
        {"name": "Lime Juice", "category": "Juice"},
        {"name": "Lemon Juice", "category": "Juice"},
        {"name": "Simple Syrup", "category": "Syrup"},
        {"name": "Angostura Bitters", "category": "Bitters"},
    ]

    for ingredient in default_ingredients:
        execute_sql_with_retry(
            "INSERT INTO ingredients (name, category) VALUES (:name, :category)",
            [
                {"name": "name", "value": {"stringValue": ingredient["name"]}},
                {"name": "category", "value": {"stringValue": ingredient["category"]}},
            ],
        )

    print("Default data added successfully!")


if __name__ == "__main__":
    print("Starting database initialization...")
    initialize_database()
