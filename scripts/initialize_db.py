import os
import time
import sqlparse

import boto3
from botocore.exceptions import ClientError

schema_path = os.path.join(os.path.dirname(__file__), "..", "cocktaildb", "schema.sql")

# Initialize boto3 clients
secretsmanager = boto3.client("secretsmanager")
rds = boto3.client("rds")
rds_data = boto3.client("rds-data")


def execute_sql_with_retry(sql, parameters=None, max_retries=5, initial_delay=1):
    """Execute SQL using RDS Data API with retry logic for database resuming"""
    secret_arn = os.environ.get("DB_SECRET_ARN")
    cluster_arn = os.environ.get("DB_CLUSTER_ARN")
    db_name = os.environ.get("DB_NAME", "cocktaildb")

    print(f"Executing SQL: {sql[:100]}{'...' if len(sql) > 100 else ''}")
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
            print(f"SQL execution successful.")
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
    """Create all tables and add default data using the SQL schema file"""
    try:
        # Drop all tables
        print("Dropping all existing tables...")
        print("Attempting to drop schema...")
        execute_sql_with_retry("DROP SCHEMA public CASCADE;")
        print("Schema dropped successfully")

        print("Creating new schema...")
        execute_sql_with_retry("CREATE SCHEMA public;")
        print("Schema created successfully")

        # Read and execute the SQL schema file
        print("Creating tables from schema.sql...")

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        # Use sqlparse to split the SQL file into statements
        statements = sqlparse.split(schema_sql)

        print(f"Found {len(statements)} SQL statements to execute")
        for i, statement in enumerate(statements):
            if statement.strip():
                print(f"Executing statement {i + 1}/{len(statements)}")
                execute_sql_with_retry(statement)
                print("SQL statement executed successfully")

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

    print("Adding default ingredient categories...")
    # Add root ingredient categories using our hierarchy functions
    default_categories = [
        {"name": "Spirits", "description": "Alcoholic distilled beverages"},
        {"name": "Mixers", "description": "Non-alcoholic ingredients"},
        {
            "name": "Garnishes",
            "description": "Decorative and flavor-enhancing additions",
        },
        {"name": "Bitters", "description": "Concentrated flavor extracts"},
    ]

    for category in default_categories:
        execute_sql_with_retry(
            "SELECT add_ingredient(:name::VARCHAR, :category::VARCHAR, :description::TEXT, :parent_id::INTEGER)",
            [
                {"name": "name", "value": {"stringValue": category["name"]}},
                {"name": "category", "value": {"isNull": True}},
                {
                    "name": "description",
                    "value": {"stringValue": category["description"]},
                },
                {"name": "parent_id", "value": {"isNull": True}},
            ],
        )

    print("Adding spirit types...")
    # Get the Spirits category ID
    spirits_result = execute_sql_with_retry(
        "SELECT id FROM ingredients WHERE name = 'Spirits'"
    )
    spirits_id = spirits_result["records"][0][0]["longValue"]

    # Add spirit subcategories
    spirit_types = [
        {"name": "Gin", "description": "Juniper-flavored spirit"},
        {"name": "Vodka", "description": "Neutral grain spirit"},
        {"name": "Rum", "description": "Sugarcane-based spirit"},
        {"name": "Tequila", "description": "Agave-based spirit"},
        {"name": "Whiskey", "description": "Grain-based aged spirit"},
    ]

    for spirit in spirit_types:
        execute_sql_with_retry(
            "SELECT add_ingredient(:name::VARCHAR, :category::VARCHAR, :description::TEXT, :parent_id::INTEGER)",
            [
                {"name": "name", "value": {"stringValue": spirit["name"]}},
                {"name": "category", "value": {"stringValue": "Spirit"}},
                {
                    "name": "description",
                    "value": {"stringValue": spirit["description"]},
                },
                {"name": "parent_id", "value": {"longValue": spirits_id}},
            ],
        )

    print("Adding mixer types...")
    # Get the Mixers category ID
    mixers_result = execute_sql_with_retry(
        "SELECT id FROM ingredients WHERE name = 'Mixers'"
    )
    mixers_id = mixers_result["records"][0][0]["longValue"]

    # Add mixer subcategories
    mixer_types = [
        {"name": "Juices", "description": "Fruit and vegetable juices"},
        {"name": "Syrups", "description": "Sweeteners and flavored syrups"},
        {"name": "Sodas", "description": "Carbonated beverages"},
    ]

    for mixer in mixer_types:
        execute_sql_with_retry(
            "SELECT add_ingredient(:name::VARCHAR, :category::VARCHAR, :description::TEXT, :parent_id::INTEGER)",
            [
                {"name": "name", "value": {"stringValue": mixer["name"]}},
                {"name": "category", "value": {"stringValue": "Mixer"}},
                {"name": "description", "value": {"stringValue": mixer["description"]}},
                {"name": "parent_id", "value": {"longValue": mixers_id}},
            ],
        )

    print("Default data added successfully!")


if __name__ == "__main__":
    print("Starting database initialization...")
    initialize_database()
