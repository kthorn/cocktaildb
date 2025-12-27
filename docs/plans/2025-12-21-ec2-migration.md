# CocktailDB EC2 Migration Implementation Plan

> **LEGACY DOCUMENT**: This migration plan was completed in December 2025. CocktailDB now runs on EC2 with PostgreSQL. SQLite references here are historical.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate CocktailDB from serverless (Lambda + EFS + Batch + VPC endpoints) to a single EC2 instance running PostgreSQL, Docker-containerized API, and Caddy reverse proxy.

**Architecture:** Single t4g.small/medium ARM Graviton EC2 instance in default VPC public subnet. PostgreSQL runs on host, API runs in Docker container, Caddy handles TLS termination and static file serving. Analytics jobs run via systemd timer. S3 backups retained with adapted backup script.

**Tech Stack:** EC2 (ARM64), PostgreSQL 16, Docker, Docker Compose, Caddy, systemd timers, Ansible, AWS CLI

---

## Prerequisites

Before starting:
- AWS CLI configured with appropriate credentials
- SSH key pair created in AWS for EC2 access
- Domain name ready for DNS update (if using custom domain)
- Current prod database backup available in S3

---

## Phase 1: Infrastructure Foundation (Ansible Playbooks)

### Task 1.1: Create Ansible Project Structure

**Files:**
- Create: `infrastructure/ansible/inventory/hosts.yml`
- Create: `infrastructure/ansible/ansible.cfg`
- Create: `infrastructure/ansible/requirements.yml`

**Step 1: Create directory structure**

```bash
mkdir -p infrastructure/ansible/{inventory,roles,playbooks,group_vars,files}
```

**Step 2: Create ansible.cfg**

```ini
# infrastructure/ansible/ansible.cfg
[defaults]
inventory = inventory/hosts.yml
remote_user = ec2-user
private_key_file = ~/.ssh/cocktaildb-ec2.pem
host_key_checking = False
roles_path = roles

[privilege_escalation]
become = True
become_method = sudo
```

**Step 3: Create inventory template**

```yaml
# infrastructure/ansible/inventory/hosts.yml
all:
  hosts:
    cocktaildb:
      ansible_host: "{{ lookup('env', 'COCKTAILDB_HOST') }}"
      ansible_user: ec2-user
  vars:
    ansible_python_interpreter: /usr/bin/python3
```

**Step 4: Create requirements.yml**

```yaml
# infrastructure/ansible/requirements.yml
collections:
  - name: community.docker
    version: ">=3.0.0"
  - name: community.postgresql
    version: ">=3.0.0"
```

**Step 5: Commit**

```bash
git add infrastructure/ansible/
git commit -m "feat: add ansible project structure for EC2 migration"
```

---

### Task 1.2: Create EC2 Launch Script

**Files:**
- Create: `infrastructure/scripts/launch-ec2.sh`

**Step 1: Write launch script**

```bash
#!/bin/bash
# infrastructure/scripts/launch-ec2.sh
# Launch EC2 instance for CocktailDB

set -euo pipefail

# Configuration
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.small}"
KEY_NAME="${KEY_NAME:-cocktaildb-ec2}"
SECURITY_GROUP_NAME="cocktaildb-server"
AMI_ID=""  # Will be looked up

# Get latest Amazon Linux 2023 ARM64 AMI
get_ami() {
    aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-arm64" \
                  "Name=state,Values=available" \
        --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
        --output text
}

# Create security group if not exists
create_security_group() {
    local vpc_id
    vpc_id=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text)

    # Check if exists
    local sg_id
    sg_id=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=${SECURITY_GROUP_NAME}" "Name=vpc-id,Values=${vpc_id}" \
        --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

    if [ "$sg_id" = "None" ] || [ -z "$sg_id" ]; then
        echo "Creating security group..."
        sg_id=$(aws ec2 create-security-group \
            --group-name "${SECURITY_GROUP_NAME}" \
            --description "CocktailDB server security group" \
            --vpc-id "${vpc_id}" \
            --query 'GroupId' --output text)

        # Add inbound rules
        aws ec2 authorize-security-group-ingress --group-id "$sg_id" \
            --protocol tcp --port 22 --cidr 0.0.0.0/0
        aws ec2 authorize-security-group-ingress --group-id "$sg_id" \
            --protocol tcp --port 80 --cidr 0.0.0.0/0
        aws ec2 authorize-security-group-ingress --group-id "$sg_id" \
            --protocol tcp --port 443 --cidr 0.0.0.0/0
    fi

    echo "$sg_id"
}

# Main
AMI_ID=$(get_ami)
echo "Using AMI: $AMI_ID"

SG_ID=$(create_security_group)
echo "Using Security Group: $SG_ID"

# Launch instance
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --associate-public-ip-address \
    --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=cocktaildb-server}]" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "Launched instance: $INSTANCE_ID"

# Wait for running
echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo "Instance is running!"
echo "Public IP: $PUBLIC_IP"
echo ""
echo "Add to inventory:"
echo "  export COCKTAILDB_HOST=$PUBLIC_IP"
echo ""
echo "SSH access:"
echo "  ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PUBLIC_IP"
```

**Step 2: Make executable**

```bash
chmod +x infrastructure/scripts/launch-ec2.sh
```

**Step 3: Commit**

```bash
git add infrastructure/scripts/launch-ec2.sh
git commit -m "feat: add EC2 launch script"
```

---

### Task 1.3: Create Base Provisioning Playbook

**Files:**
- Create: `infrastructure/ansible/playbooks/provision.yml`
- Create: `infrastructure/ansible/group_vars/all.yml`

**Step 1: Create group variables**

```yaml
# infrastructure/ansible/group_vars/all.yml
---
# Application settings
app_name: cocktaildb
app_user: cocktaildb
app_group: cocktaildb
app_home: /opt/cocktaildb

# Database settings
db_name: cocktaildb
db_user: cocktaildb
db_password: "{{ lookup('env', 'COCKTAILDB_DB_PASSWORD') }}"

# Docker settings
docker_compose_version: "2.24.0"

# Caddy settings
domain_name: "{{ lookup('env', 'COCKTAILDB_DOMAIN') | default('localhost', true) }}"

# S3 settings
backup_bucket: "{{ lookup('env', 'COCKTAILDB_BACKUP_BUCKET') }}"
analytics_bucket: "{{ lookup('env', 'COCKTAILDB_ANALYTICS_BUCKET') }}"

# AWS region
aws_region: "{{ lookup('env', 'AWS_REGION') | default('us-east-1', true) }}"
```

**Step 2: Create provision playbook**

```yaml
# infrastructure/ansible/playbooks/provision.yml
---
- name: Provision CocktailDB server
  hosts: cocktaildb
  become: yes

  vars:
    packages:
      - docker
      - postgresql16-server
      - postgresql16
      - python3
      - python3-pip
      - git
      - htop
      - tmux

  tasks:
    - name: Update system packages
      dnf:
        name: "*"
        state: latest

    - name: Install required packages
      dnf:
        name: "{{ packages }}"
        state: present

    # Docker setup
    - name: Start and enable Docker
      systemd:
        name: docker
        state: started
        enabled: yes

    - name: Add ec2-user to docker group
      user:
        name: ec2-user
        groups: docker
        append: yes

    # Create app user
    - name: Create application user
      user:
        name: "{{ app_user }}"
        system: yes
        home: "{{ app_home }}"
        shell: /bin/bash

    - name: Add app user to docker group
      user:
        name: "{{ app_user }}"
        groups: docker
        append: yes

    # PostgreSQL setup
    - name: Initialize PostgreSQL database
      command: postgresql-setup --initdb
      args:
        creates: /var/lib/pgsql/data/PG_VERSION

    - name: Configure PostgreSQL to listen on localhost only
      lineinfile:
        path: /var/lib/pgsql/data/postgresql.conf
        regexp: "^#?listen_addresses"
        line: "listen_addresses = '127.0.0.1'"
      notify: Restart PostgreSQL

    - name: Configure PostgreSQL authentication
      copy:
        dest: /var/lib/pgsql/data/pg_hba.conf
        content: |
          # TYPE  DATABASE        USER            ADDRESS                 METHOD
          local   all             postgres                                peer
          local   all             all                                     md5
          host    all             all             127.0.0.1/32            md5
        owner: postgres
        group: postgres
        mode: '0600'
      notify: Restart PostgreSQL

    - name: Start and enable PostgreSQL
      systemd:
        name: postgresql
        state: started
        enabled: yes

    # Create application directories
    - name: Create application directories
      file:
        path: "{{ item }}"
        state: directory
        owner: "{{ app_user }}"
        group: "{{ app_group }}"
        mode: '0755'
      loop:
        - "{{ app_home }}"
        - "{{ app_home }}/api"
        - "{{ app_home }}/backups"
        - "{{ app_home }}/logs"

    # Install Caddy
    - name: Install Caddy repository
      shell: |
        dnf install -y 'dnf-command(copr)'
        dnf copr enable -y @caddy/caddy
      args:
        creates: /etc/yum.repos.d/_copr:copr.fedorainfracloud.org:group_caddy:caddy.repo

    - name: Install Caddy
      dnf:
        name: caddy
        state: present

    - name: Start and enable Caddy
      systemd:
        name: caddy
        state: started
        enabled: yes

  handlers:
    - name: Restart PostgreSQL
      systemd:
        name: postgresql
        state: restarted
```

**Step 3: Commit**

```bash
git add infrastructure/ansible/
git commit -m "feat: add base provisioning playbook"
```

---

### Task 1.4: Create Database Setup Playbook

**Files:**
- Create: `infrastructure/ansible/playbooks/setup-database.yml`

**Step 1: Write database setup playbook**

```yaml
# infrastructure/ansible/playbooks/setup-database.yml
---
- name: Setup PostgreSQL database for CocktailDB
  hosts: cocktaildb
  become: yes
  become_user: postgres

  vars:
    db_name: cocktaildb
    db_user: cocktaildb
    db_password: "{{ lookup('env', 'COCKTAILDB_DB_PASSWORD') }}"

  tasks:
    - name: Create database user
      community.postgresql.postgresql_user:
        name: "{{ db_user }}"
        password: "{{ db_password }}"
        state: present

    - name: Create database
      community.postgresql.postgresql_db:
        name: "{{ db_name }}"
        owner: "{{ db_user }}"
        encoding: UTF8
        state: present

    - name: Grant privileges
      community.postgresql.postgresql_privs:
        db: "{{ db_name }}"
        role: "{{ db_user }}"
        privs: ALL
        type: database
        state: present
```

**Step 2: Commit**

```bash
git add infrastructure/ansible/playbooks/setup-database.yml
git commit -m "feat: add PostgreSQL database setup playbook"
```

---

## Phase 2: Database Migration (SQLite to PostgreSQL)

### Task 2.1: Create PostgreSQL Schema

**Files:**
- Create: `infrastructure/postgres/schema.sql`

**Step 1: Write PostgreSQL-compatible schema**

```sql
-- infrastructure/postgres/schema.sql
-- PostgreSQL Schema for CocktailDB
-- Converted from SQLite schema

-- Extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search

-- Table Definitions
CREATE TABLE IF NOT EXISTS ingredients (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  parent_id INTEGER REFERENCES ingredients(id),
  path TEXT,
  allow_substitution BOOLEAN NOT NULL DEFAULT FALSE,
  created_by TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS units (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  abbreviation TEXT,
  conversion_to_ml REAL
);

CREATE TABLE IF NOT EXISTS recipes (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  instructions TEXT,
  description TEXT,
  image_url TEXT,
  source TEXT,
  source_url TEXT,
  avg_rating REAL DEFAULT 0,
  rating_count INTEGER DEFAULT 0,
  created_by TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ratings (
  id SERIAL PRIMARY KEY,
  cognito_user_id TEXT NOT NULL,
  cognito_username TEXT NOT NULL,
  recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  UNIQUE(cognito_user_id, recipe_id)
);

CREATE TABLE IF NOT EXISTS tags (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  created_by TEXT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipe_tags (
  id SERIAL PRIMARY KEY,
  recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  UNIQUE(recipe_id, tag_id)
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
  id SERIAL PRIMARY KEY,
  recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
  unit_id INTEGER REFERENCES units(id) ON DELETE SET NULL,
  amount REAL
);

CREATE TABLE IF NOT EXISTS user_ingredients (
  id SERIAL PRIMARY KEY,
  cognito_user_id TEXT NOT NULL,
  ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(cognito_user_id, ingredient_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ingredients_parent_id ON ingredients(parent_id);
CREATE INDEX IF NOT EXISTS idx_ingredients_path ON ingredients(path);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe_id ON recipe_ingredients(recipe_id);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_ingredient_id ON recipe_ingredients(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_recipe_tags_recipe_id ON recipe_tags(recipe_id);
CREATE INDEX IF NOT EXISTS idx_recipe_tags_tag_id ON recipe_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_ratings_cognito_user_id ON ratings(cognito_user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_recipe_id ON ratings(recipe_id);
CREATE INDEX IF NOT EXISTS idx_user_ingredients_cognito_user_id ON user_ingredients(cognito_user_id);
CREATE INDEX IF NOT EXISTS idx_user_ingredients_ingredient_id ON user_ingredients(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_recipes_created_by ON recipes(created_by);
CREATE INDEX IF NOT EXISTS idx_ingredients_created_by ON ingredients(created_by);
CREATE INDEX IF NOT EXISTS idx_tags_created_by ON tags(created_by);

-- Partial unique indexes for tags
CREATE UNIQUE INDEX IF NOT EXISTS idx_public_tags ON tags(name) WHERE created_by IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_private_tags ON tags(name, created_by) WHERE created_by IS NOT NULL;

-- Text search indexes
CREATE INDEX IF NOT EXISTS idx_recipes_name_trgm ON recipes USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ingredients_name_trgm ON ingredients USING gin(name gin_trgm_ops);

-- Functions for triggers
CREATE OR REPLACE FUNCTION update_recipe_rating()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE recipes
  SET
    avg_rating = COALESCE((SELECT AVG(rating)::REAL FROM ratings WHERE recipe_id = COALESCE(NEW.recipe_id, OLD.recipe_id)), 0),
    rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = COALESCE(NEW.recipe_id, OLD.recipe_id))
  WHERE id = COALESCE(NEW.recipe_id, OLD.recipe_id);
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers
DROP TRIGGER IF EXISTS update_avg_rating_insert ON ratings;
CREATE TRIGGER update_avg_rating_insert
AFTER INSERT ON ratings
FOR EACH ROW EXECUTE FUNCTION update_recipe_rating();

DROP TRIGGER IF EXISTS update_avg_rating_update ON ratings;
CREATE TRIGGER update_avg_rating_update
AFTER UPDATE ON ratings
FOR EACH ROW EXECUTE FUNCTION update_recipe_rating();

DROP TRIGGER IF EXISTS update_avg_rating_delete ON ratings;
CREATE TRIGGER update_avg_rating_delete
AFTER DELETE ON ratings
FOR EACH ROW EXECUTE FUNCTION update_recipe_rating();

DROP TRIGGER IF EXISTS update_recipes_updated_at ON recipes;
CREATE TRIGGER update_recipes_updated_at
BEFORE UPDATE ON recipes
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS update_ingredients_updated_at ON ingredients;
CREATE TRIGGER update_ingredients_updated_at
BEFORE UPDATE ON ingredients
FOR EACH ROW EXECUTE FUNCTION update_timestamp();
```

**Step 2: Commit**

```bash
git add infrastructure/postgres/schema.sql
git commit -m "feat: add PostgreSQL schema for EC2 migration"
```

---

### Task 2.2: Create Migration Script

**Files:**
- Create: `infrastructure/scripts/migrate-sqlite-to-postgres.py`

**Step 1: Write migration script**

```python
#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL.
Downloads SQLite backup from S3, transforms data, and inserts into PostgreSQL.
"""
import argparse
import os
import sqlite3
import subprocess
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

    columns = rows[0].keys()
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
    placeholders = ', '.join(['%s'] * len(columns))

    # Use execute_values for bulk insert
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


def migrate(sqlite_path: str, pg_conn_str: str):
    """Migrate all data from SQLite to PostgreSQL."""
    pg_conn = psycopg2.connect(pg_conn_str)

    for table in TABLES:
        print(f"Migrating {table}...")
        columns, data = get_sqlite_data(sqlite_path, table)
        insert_postgres_data(pg_conn, table, columns, data)

    pg_conn.close()
    print("Migration complete!")


def main():
    parser = argparse.ArgumentParser(description='Migrate SQLite to PostgreSQL')
    parser.add_argument('--sqlite', help='Path to SQLite database')
    parser.add_argument('--s3-bucket', help='S3 bucket with backups')
    parser.add_argument('--pg-host', default='localhost')
    parser.add_argument('--pg-port', default='5432')
    parser.add_argument('--pg-db', default='cocktaildb')
    parser.add_argument('--pg-user', default='cocktaildb')
    parser.add_argument('--pg-password', required=True)

    args = parser.parse_args()

    # Get SQLite database
    if args.sqlite:
        sqlite_path = args.sqlite
    elif args.s3_bucket:
        sqlite_path = '/tmp/cocktaildb_backup.db'
        download_latest_backup(args.s3_bucket, sqlite_path)
    else:
        print("Error: Must provide --sqlite or --s3-bucket")
        sys.exit(1)

    # Build PostgreSQL connection string
    pg_conn_str = f"host={args.pg_host} port={args.pg_port} dbname={args.pg_db} user={args.pg_user} password={args.pg_password}"

    migrate(sqlite_path, pg_conn_str)


if __name__ == '__main__':
    main()
```

**Step 2: Make executable**

```bash
chmod +x infrastructure/scripts/migrate-sqlite-to-postgres.py
```

**Step 3: Commit**

```bash
git add infrastructure/scripts/migrate-sqlite-to-postgres.py
git commit -m "feat: add SQLite to PostgreSQL migration script"
```

---

### Task 2.3: Create Database Abstraction Layer

**Files:**
- Modify: `api/db/db_core.py`
- Create: `api/db/postgres_backend.py`
- Create: `api/db/sqlite_backend.py`

**Step 1: Create database backend interface**

Create `api/db/backend_base.py`:

```python
"""Abstract base class for database backends."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DatabaseBackend(ABC):
    """Abstract database backend interface."""

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        pass

    @abstractmethod
    def execute_returning_id(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT and return the new row's ID."""
        pass

    @abstractmethod
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute a query with multiple parameter sets."""
        pass

    @abstractmethod
    def close(self):
        """Close the database connection."""
        pass

    @property
    @abstractmethod
    def placeholder(self) -> str:
        """Return the parameter placeholder style ('?' for SQLite, '%s' for PostgreSQL)."""
        pass
```

**Step 2: Create SQLite backend**

Create `api/db/sqlite_backend.py`:

```python
"""SQLite database backend."""
import functools
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List

from .backend_base import DatabaseBackend

logger = logging.getLogger(__name__)


def retry_on_db_locked(max_retries=3, initial_backoff=0.1):
    """Decorator to retry operations when database is locked."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            backoff = initial_backoff
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"Database locked, retry {attempt + 1}/{max_retries}")
                        time.sleep(backoff)
                        backoff *= 2
                    else:
                        raise
        return wrapper
    return decorator


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend implementation."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("DB_PATH", "/mnt/efs/cocktaildb.db")
        self._connection = None
        self._test_connection()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, uri=True)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _test_connection(self):
        """Test database connectivity."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1")
        cursor.close()

    @property
    def placeholder(self) -> str:
        return "?"

    @retry_on_db_locked()
    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(query, params)

        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
        else:
            self.connection.commit()
            result = [{"rowcount": cursor.rowcount}]

        cursor.close()
        return result

    @retry_on_db_locked()
    def execute_returning_id(self, query: str, params: tuple = ()) -> int:
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        self.connection.commit()
        row_id = cursor.lastrowid
        cursor.close()
        return row_id

    @retry_on_db_locked()
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        cursor = self.connection.cursor()
        cursor.executemany(query, params_list)
        self.connection.commit()
        count = cursor.rowcount
        cursor.close()
        return count

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None
```

**Step 3: Create PostgreSQL backend**

Create `api/db/postgres_backend.py`:

```python
"""PostgreSQL database backend."""
import logging
import os
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor

from .backend_base import DatabaseBackend

logger = logging.getLogger(__name__)


class PostgresBackend(DatabaseBackend):
    """PostgreSQL database backend implementation."""

    def __init__(self):
        self.conn_params = {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'port': os.environ.get('DB_PORT', '5432'),
            'dbname': os.environ.get('DB_NAME', 'cocktaildb'),
            'user': os.environ.get('DB_USER', 'cocktaildb'),
            'password': os.environ.get('DB_PASSWORD', ''),
        }
        self._connection = None
        self._test_connection()

    @property
    def connection(self):
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(**self.conn_params)
        return self._connection

    def _test_connection(self):
        """Test database connectivity."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1")
        cursor.close()

    @property
    def placeholder(self) -> str:
        return "%s"

    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        # Convert ? placeholders to %s for PostgreSQL
        query = query.replace("?", "%s")

        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params)

        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
        else:
            self.connection.commit()
            result = [{"rowcount": cursor.rowcount}]

        cursor.close()
        return result

    def execute_returning_id(self, query: str, params: tuple = ()) -> int:
        # Convert ? placeholders to %s for PostgreSQL
        query = query.replace("?", "%s")

        # Add RETURNING clause if not present
        if "RETURNING" not in query.upper():
            query = query.rstrip(";") + " RETURNING id"

        cursor = self.connection.cursor()
        cursor.execute(query, params)
        row_id = cursor.fetchone()[0]
        self.connection.commit()
        cursor.close()
        return row_id

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        # Convert ? placeholders to %s for PostgreSQL
        query = query.replace("?", "%s")

        cursor = self.connection.cursor()
        cursor.executemany(query, params_list)
        self.connection.commit()
        count = cursor.rowcount
        cursor.close()
        return count

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None
```

**Step 4: Update database.py to use backend factory**

Modify `api/db/database.py`:

```python
"""Database dependency for FastAPI."""
import logging
import os
import time
from typing import Optional

from .db_core import Database

logger = logging.getLogger(__name__)

# Global database instance cache
_DB_INSTANCE: Optional[Database] = None
_DB_INSTANCE_TIME: float = 0
_CACHE_DURATION = 300  # 5 minutes


def get_database() -> Database:
    """Get or create cached database instance."""
    global _DB_INSTANCE, _DB_INSTANCE_TIME

    current_time = time.time()

    if _DB_INSTANCE is None or (current_time - _DB_INSTANCE_TIME) > _CACHE_DURATION:
        logger.info("Creating new database instance")
        _DB_INSTANCE = Database()
        _DB_INSTANCE_TIME = current_time

    return _DB_INSTANCE


def get_backend():
    """Factory function to get appropriate database backend."""
    db_type = os.environ.get('DB_TYPE', 'sqlite').lower()

    if db_type == 'postgres' or db_type == 'postgresql':
        from .postgres_backend import PostgresBackend
        return PostgresBackend()
    else:
        from .sqlite_backend import SQLiteBackend
        return SQLiteBackend()
```

**Step 5: Commit**

```bash
git add api/db/
git commit -m "feat: add database backend abstraction for SQLite/PostgreSQL"
```

---

## Phase 3: API Containerization

### Task 3.1: Create Production Dockerfile

**Files:**
- Create: `api/Dockerfile.prod`

**Step 1: Write production Dockerfile**

```dockerfile
# api/Dockerfile.prod
# Production Dockerfile for CocktailDB API

FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt

# Production stage
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appuser . .

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**Step 2: Create requirements-prod.txt**

```text
# api/requirements-prod.txt
# Production-only dependencies
psycopg2-binary==2.9.9
uvicorn[standard]==0.24.0
gunicorn==21.2.0
```

**Step 3: Commit**

```bash
git add api/Dockerfile.prod api/requirements-prod.txt
git commit -m "feat: add production Dockerfile for EC2 deployment"
```

---

### Task 3.2: Create Docker Compose Configuration

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.prod.yml`

**Step 1: Write base docker-compose.yml**

```yaml
# docker-compose.yml
# Base Docker Compose configuration

services:
  api:
    build:
      context: ./api
      dockerfile: Dockerfile.prod
    environment:
      - DB_TYPE=postgres
      - DB_HOST=host.docker.internal
      - DB_PORT=5432
      - DB_NAME=cocktaildb
      - DB_USER=cocktaildb
      - DB_PASSWORD=${DB_PASSWORD}
      - ANALYTICS_BUCKET=${ANALYTICS_BUCKET}
      - AWS_REGION=${AWS_REGION:-us-east-1}
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
    ports:
      - "127.0.0.1:8000:8000"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

**Step 2: Write production override**

```yaml
# docker-compose.prod.yml
# Production overrides

services:
  api:
    image: cocktaildb-api:latest
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

**Step 3: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml
git commit -m "feat: add Docker Compose configuration"
```

---

### Task 3.3: Add Health Check Endpoint

**Files:**
- Modify: `api/main.py`

**Step 1: Add health check route to main.py**

Add after the existing routes:

```python
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
```

**Step 2: Add import**

Add to imports in main.py:
```python
from datetime import datetime
```

**Step 3: Commit**

```bash
git add api/main.py
git commit -m "feat: add health check endpoint"
```

---

## Phase 4: Reverse Proxy Configuration

### Task 4.1: Create Caddy Configuration

**Files:**
- Create: `infrastructure/caddy/Caddyfile`

**Step 1: Write Caddyfile**

```caddyfile
# infrastructure/caddy/Caddyfile
# Caddy configuration for CocktailDB

{
    email admin@{$DOMAIN_NAME}
    admin off
}

{$DOMAIN_NAME} {
    # API proxy
    handle /api/* {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # Static files (frontend)
    handle {
        root * /opt/cocktaildb/web
        file_server
        try_files {path} /index.html
    }

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }

    # Logging
    log {
        output file /var/log/caddy/access.log {
            roll_size 10mb
            roll_keep 5
        }
    }
}

# Localhost fallback for development/testing
:80 {
    handle /api/* {
        reverse_proxy localhost:8000
    }

    handle {
        root * /opt/cocktaildb/web
        file_server
        try_files {path} /index.html
    }
}
```

**Step 2: Commit**

```bash
git add infrastructure/caddy/Caddyfile
git commit -m "feat: add Caddy reverse proxy configuration"
```

---

### Task 4.2: Create Caddy Deployment Playbook

**Files:**
- Create: `infrastructure/ansible/playbooks/deploy-caddy.yml`

**Step 1: Write Caddy deployment playbook**

```yaml
# infrastructure/ansible/playbooks/deploy-caddy.yml
---
- name: Deploy Caddy configuration
  hosts: cocktaildb
  become: yes

  vars:
    domain_name: "{{ lookup('env', 'COCKTAILDB_DOMAIN') }}"
    caddy_config_dir: /etc/caddy
    web_root: /opt/cocktaildb/web

  tasks:
    - name: Create Caddy log directory
      file:
        path: /var/log/caddy
        state: directory
        owner: caddy
        group: caddy
        mode: '0755'

    - name: Create web root directory
      file:
        path: "{{ web_root }}"
        state: directory
        owner: cocktaildb
        group: cocktaildb
        mode: '0755'

    - name: Deploy Caddyfile
      template:
        src: ../files/Caddyfile.j2
        dest: "{{ caddy_config_dir }}/Caddyfile"
        owner: root
        group: root
        mode: '0644'
      notify: Reload Caddy

    - name: Create Caddy environment file
      copy:
        dest: /etc/caddy/caddy.env
        content: |
          DOMAIN_NAME={{ domain_name }}
        owner: root
        group: root
        mode: '0644'
      notify: Reload Caddy

    - name: Configure Caddy systemd override
      copy:
        dest: /etc/systemd/system/caddy.service.d/override.conf
        content: |
          [Service]
          EnvironmentFile=/etc/caddy/caddy.env
        owner: root
        group: root
        mode: '0644'
      notify:
        - Daemon reload
        - Restart Caddy

  handlers:
    - name: Daemon reload
      systemd:
        daemon_reload: yes

    - name: Reload Caddy
      systemd:
        name: caddy
        state: reloaded

    - name: Restart Caddy
      systemd:
        name: caddy
        state: restarted
```

**Step 2: Create Caddyfile template**

```bash
mkdir -p infrastructure/ansible/files
cp infrastructure/caddy/Caddyfile infrastructure/ansible/files/Caddyfile.j2
```

**Step 3: Commit**

```bash
git add infrastructure/ansible/
git commit -m "feat: add Caddy deployment playbook"
```

---

## Phase 5: Analytics Migration

### Task 5.1: Create Analytics Systemd Service

**Files:**
- Create: `infrastructure/systemd/cocktaildb-analytics.service`
- Create: `infrastructure/systemd/cocktaildb-analytics.timer`

**Step 1: Write systemd service**

```ini
# infrastructure/systemd/cocktaildb-analytics.service
[Unit]
Description=CocktailDB Analytics Refresh
After=network.target postgresql.service docker.service

[Service]
Type=oneshot
User=cocktaildb
Group=cocktaildb
WorkingDirectory=/opt/cocktaildb

# Load environment
EnvironmentFile=/opt/cocktaildb/.env

# Run analytics refresh
ExecStart=/usr/bin/docker compose run --rm api python -m analytics.analytics_refresh

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cocktaildb-analytics

# Timeout (1 hour max)
TimeoutStartSec=3600
```

**Step 2: Write systemd timer**

```ini
# infrastructure/systemd/cocktaildb-analytics.timer
[Unit]
Description=Run CocktailDB Analytics Refresh Daily

[Timer]
# Run at 4 AM daily
OnCalendar=*-*-* 04:00:00
# Run on boot if missed
Persistent=true
# Randomize start by up to 30 minutes
RandomizedDelaySec=1800

[Install]
WantedBy=timers.target
```

**Step 3: Commit**

```bash
git add infrastructure/systemd/
git commit -m "feat: add systemd timer for analytics refresh"
```

---

### Task 5.2: Update Analytics Refresh for Local Execution

**Files:**
- Modify: `api/analytics/analytics_refresh.py`

**Step 1: Add direct database support**

Update the `regenerate_analytics` function to optionally use local database:

```python
def regenerate_analytics(use_s3: bool = True) -> Dict[str, Any]:
    """
    Core analytics regeneration logic.

    Args:
        use_s3: If True, store results in S3. If False, store locally.
    """
    bucket_name = os.environ.get('ANALYTICS_BUCKET')
    local_output = os.environ.get('ANALYTICS_OUTPUT_DIR', '/opt/cocktaildb/analytics')

    if use_s3 and not bucket_name:
        raise ValueError("ANALYTICS_BUCKET environment variable not set")

    # ... rest of function, with conditional storage
```

**Step 2: Commit**

```bash
git add api/analytics/analytics_refresh.py
git commit -m "feat: support local analytics output"
```

---

### Task 5.3: Create On-Demand Analytics Trigger

**Files:**
- Create: `infrastructure/scripts/trigger-analytics.sh`

**Step 1: Write trigger script**

```bash
#!/bin/bash
# infrastructure/scripts/trigger-analytics.sh
# Trigger analytics refresh on EC2 instance

set -euo pipefail

cd /opt/cocktaildb

# Run analytics in Docker
docker compose run --rm api python -m analytics.analytics_refresh

echo "Analytics refresh complete"
```

**Step 2: Make executable**

```bash
chmod +x infrastructure/scripts/trigger-analytics.sh
```

**Step 3: Commit**

```bash
git add infrastructure/scripts/trigger-analytics.sh
git commit -m "feat: add on-demand analytics trigger script"
```

---

## Phase 6: Backup System

### Task 6.1: Create PostgreSQL Backup Script

**Files:**
- Create: `infrastructure/scripts/backup-postgres.sh`

**Step 1: Write backup script**

```bash
#!/bin/bash
# infrastructure/scripts/backup-postgres.sh
# Backup PostgreSQL database to S3

set -euo pipefail

# Configuration
DB_NAME="${DB_NAME:-cocktaildb}"
DB_USER="${DB_USER:-cocktaildb}"
BACKUP_BUCKET="${BACKUP_BUCKET:-}"
BACKUP_DIR="/opt/cocktaildb/backups"
RETENTION_DAYS=30

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Generate backup filename
TIMESTAMP=$(date -u +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="backup-${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

echo "Starting PostgreSQL backup: ${BACKUP_FILE}"

# Create backup
pg_dump -U "$DB_USER" -h localhost "$DB_NAME" | gzip > "$BACKUP_PATH"

echo "Backup created: $(du -h "$BACKUP_PATH" | cut -f1)"

# Upload to S3 if bucket configured
if [ -n "$BACKUP_BUCKET" ]; then
    echo "Uploading to s3://${BACKUP_BUCKET}/${BACKUP_FILE}"
    aws s3 cp "$BACKUP_PATH" "s3://${BACKUP_BUCKET}/${BACKUP_FILE}"
    echo "Upload complete"
fi

# Clean up old local backups
echo "Cleaning up backups older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -name "backup-*.sql.gz" -mtime +${RETENTION_DAYS} -delete

# Clean up old S3 backups (optional, can also use S3 lifecycle policy)
if [ -n "$BACKUP_BUCKET" ]; then
    CUTOFF_DATE=$(date -u -d "${RETENTION_DAYS} days ago" +"%Y-%m-%d")
    aws s3 ls "s3://${BACKUP_BUCKET}/" | while read -r line; do
        FILE_DATE=$(echo "$line" | awk '{print $1}')
        FILE_NAME=$(echo "$line" | awk '{print $4}')
        if [[ "$FILE_DATE" < "$CUTOFF_DATE" ]] && [[ "$FILE_NAME" == backup-* ]]; then
            echo "Deleting old backup: $FILE_NAME"
            aws s3 rm "s3://${BACKUP_BUCKET}/${FILE_NAME}"
        fi
    done
fi

echo "Backup complete: ${BACKUP_FILE}"
```

**Step 2: Make executable**

```bash
chmod +x infrastructure/scripts/backup-postgres.sh
```

**Step 3: Commit**

```bash
git add infrastructure/scripts/backup-postgres.sh
git commit -m "feat: add PostgreSQL backup script"
```

---

### Task 6.2: Create Backup Systemd Timer

**Files:**
- Create: `infrastructure/systemd/cocktaildb-backup.service`
- Create: `infrastructure/systemd/cocktaildb-backup.timer`

**Step 1: Write backup service**

```ini
# infrastructure/systemd/cocktaildb-backup.service
[Unit]
Description=CocktailDB Database Backup
After=postgresql.service

[Service]
Type=oneshot
User=cocktaildb
Group=cocktaildb

EnvironmentFile=/opt/cocktaildb/.env
ExecStart=/opt/cocktaildb/scripts/backup-postgres.sh

StandardOutput=journal
StandardError=journal
SyslogIdentifier=cocktaildb-backup
```

**Step 2: Write backup timer**

```ini
# infrastructure/systemd/cocktaildb-backup.timer
[Unit]
Description=Run CocktailDB Backup Daily

[Timer]
# Run at 8 AM UTC daily
OnCalendar=*-*-* 08:00:00
Persistent=true
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
```

**Step 3: Commit**

```bash
git add infrastructure/systemd/
git commit -m "feat: add backup systemd timer"
```

---

## Phase 7: Deployment Automation

### Task 7.1: Create Full Deployment Playbook

**Files:**
- Create: `infrastructure/ansible/playbooks/deploy.yml`

**Step 1: Write deployment playbook**

```yaml
# infrastructure/ansible/playbooks/deploy.yml
---
- name: Deploy CocktailDB Application
  hosts: cocktaildb
  become: yes

  vars:
    app_home: /opt/cocktaildb
    app_user: cocktaildb

  tasks:
    # Copy application files
    - name: Sync API code
      synchronize:
        src: "{{ playbook_dir }}/../../../api/"
        dest: "{{ app_home }}/api/"
        delete: yes
        rsync_opts:
          - "--exclude=__pycache__"
          - "--exclude=*.pyc"
          - "--exclude=.pytest_cache"
      notify: Restart API

    - name: Sync frontend code
      synchronize:
        src: "{{ playbook_dir }}/../../../src/web/"
        dest: "{{ app_home }}/web/"
        delete: yes
      notify: Reload Caddy

    - name: Copy docker-compose files
      copy:
        src: "{{ item }}"
        dest: "{{ app_home }}/"
        owner: "{{ app_user }}"
        group: "{{ app_user }}"
        mode: '0644'
      loop:
        - "{{ playbook_dir }}/../../../docker-compose.yml"
        - "{{ playbook_dir }}/../../../docker-compose.prod.yml"
      notify: Restart API

    - name: Copy deployment scripts
      copy:
        src: "{{ playbook_dir }}/../scripts/"
        dest: "{{ app_home }}/scripts/"
        owner: "{{ app_user }}"
        group: "{{ app_user }}"
        mode: '0755'

    - name: Copy systemd units
      copy:
        src: "{{ playbook_dir }}/../systemd/"
        dest: /etc/systemd/system/
        owner: root
        group: root
        mode: '0644'
      notify: Daemon reload

    - name: Create environment file
      template:
        src: env.j2
        dest: "{{ app_home }}/.env"
        owner: "{{ app_user }}"
        group: "{{ app_user }}"
        mode: '0600'

    - name: Build Docker image
      community.docker.docker_image:
        name: cocktaildb-api
        tag: latest
        source: build
        build:
          path: "{{ app_home }}/api"
          dockerfile: Dockerfile.prod
        force_source: yes

    - name: Enable and start systemd timers
      systemd:
        name: "{{ item }}"
        enabled: yes
        state: started
      loop:
        - cocktaildb-backup.timer
        - cocktaildb-analytics.timer

  handlers:
    - name: Daemon reload
      systemd:
        daemon_reload: yes

    - name: Restart API
      shell: |
        cd {{ app_home }}
        docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate

    - name: Reload Caddy
      systemd:
        name: caddy
        state: reloaded
```

**Step 2: Create environment template**

```jinja2
# infrastructure/ansible/files/env.j2
# CocktailDB Environment Configuration
DB_TYPE=postgres
DB_HOST=localhost
DB_PORT=5432
DB_NAME={{ db_name }}
DB_USER={{ db_user }}
DB_PASSWORD={{ db_password }}

ANALYTICS_BUCKET={{ analytics_bucket }}
BACKUP_BUCKET={{ backup_bucket }}
AWS_REGION={{ aws_region }}

ENVIRONMENT=production
LOG_LEVEL=INFO

# Cognito (keep for auth)
USER_POOL_ID={{ user_pool_id }}
APP_CLIENT_ID={{ app_client_id }}
```

**Step 3: Commit**

```bash
git add infrastructure/ansible/
git commit -m "feat: add full deployment playbook"
```

---

### Task 7.2: Create Deploy Script

**Files:**
- Create: `scripts/deploy-ec2.sh`

**Step 1: Write deploy script**

```bash
#!/bin/bash
# scripts/deploy-ec2.sh
# Deploy CocktailDB to EC2 instance

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ANSIBLE_DIR="${PROJECT_ROOT}/infrastructure/ansible"

# Check required environment variables
: "${COCKTAILDB_HOST:?Must set COCKTAILDB_HOST}"
: "${COCKTAILDB_DB_PASSWORD:?Must set COCKTAILDB_DB_PASSWORD}"

# Default values
export COCKTAILDB_DOMAIN="${COCKTAILDB_DOMAIN:-}"
export AWS_REGION="${AWS_REGION:-us-east-1}"

echo "=== CocktailDB EC2 Deployment ==="
echo "Target host: $COCKTAILDB_HOST"
echo "Domain: ${COCKTAILDB_DOMAIN:-localhost}"
echo ""

# Install Ansible requirements
echo "Installing Ansible requirements..."
ansible-galaxy collection install -r "${ANSIBLE_DIR}/requirements.yml"

# Run deployment
echo "Running deployment playbook..."
cd "$ANSIBLE_DIR"
ansible-playbook playbooks/deploy.yml -v

echo ""
echo "=== Deployment Complete ==="
echo "Application URL: https://${COCKTAILDB_DOMAIN:-$COCKTAILDB_HOST}"
```

**Step 2: Make executable**

```bash
chmod +x scripts/deploy-ec2.sh
```

**Step 3: Commit**

```bash
git add scripts/deploy-ec2.sh
git commit -m "feat: add EC2 deploy script"
```

---

## Phase 8: DNS Cutover and Testing

### Task 8.1: Create DNS Update Script

**Files:**
- Create: `infrastructure/scripts/update-dns.sh`

**Step 1: Write DNS update script**

```bash
#!/bin/bash
# infrastructure/scripts/update-dns.sh
# Update Route53 DNS to point to EC2 instance

set -euo pipefail

: "${HOSTED_ZONE_ID:?Must set HOSTED_ZONE_ID}"
: "${DOMAIN_NAME:?Must set DOMAIN_NAME}"
: "${EC2_PUBLIC_IP:?Must set EC2_PUBLIC_IP}"

echo "Updating DNS: ${DOMAIN_NAME} -> ${EC2_PUBLIC_IP}"

# Create change batch
CHANGE_BATCH=$(cat <<EOF
{
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "${DOMAIN_NAME}",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          {"Value": "${EC2_PUBLIC_IP}"}
        ]
      }
    }
  ]
}
EOF
)

# Submit change
CHANGE_ID=$(aws route53 change-resource-record-sets \
    --hosted-zone-id "$HOSTED_ZONE_ID" \
    --change-batch "$CHANGE_BATCH" \
    --query 'ChangeInfo.Id' \
    --output text)

echo "Change submitted: $CHANGE_ID"

# Wait for propagation
echo "Waiting for DNS propagation..."
aws route53 wait resource-record-sets-changed --id "$CHANGE_ID"

echo "DNS update complete!"
```

**Step 2: Make executable and commit**

```bash
chmod +x infrastructure/scripts/update-dns.sh
git add infrastructure/scripts/update-dns.sh
git commit -m "feat: add DNS update script"
```

---

### Task 8.2: Create Smoke Test Script

**Files:**
- Create: `infrastructure/scripts/smoke-test.sh`

**Step 1: Write smoke test script**

```bash
#!/bin/bash
# infrastructure/scripts/smoke-test.sh
# Smoke tests for CocktailDB deployment

set -euo pipefail

BASE_URL="${1:-http://localhost}"

echo "=== CocktailDB Smoke Tests ==="
echo "Base URL: $BASE_URL"
echo ""

PASS=0
FAIL=0

test_endpoint() {
    local name="$1"
    local endpoint="$2"
    local expected_status="${3:-200}"

    echo -n "Testing $name... "

    status=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${endpoint}" || echo "000")

    if [ "$status" = "$expected_status" ]; then
        echo "PASS (HTTP $status)"
        ((PASS++))
    else
        echo "FAIL (expected $expected_status, got $status)"
        ((FAIL++))
    fi
}

# Health check
test_endpoint "Health check" "/health"

# API endpoints
test_endpoint "Recipes list" "/api/v1/recipes"
test_endpoint "Ingredients list" "/api/v1/ingredients"
test_endpoint "Units list" "/api/v1/units"
test_endpoint "Analytics - ingredient usage" "/api/v1/analytics/ingredient-usage"

# Static content
test_endpoint "Frontend index" "/"
test_endpoint "Frontend JS" "/js/app.js"

echo ""
echo "=== Results ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [ $FAIL -gt 0 ]; then
    exit 1
fi

echo "All tests passed!"
```

**Step 2: Make executable and commit**

```bash
chmod +x infrastructure/scripts/smoke-test.sh
git add infrastructure/scripts/smoke-test.sh
git commit -m "feat: add smoke test script"
```

---

## Phase 9: Serverless Teardown

### Task 9.1: Document Teardown Procedure

**Files:**
- Create: `docs/serverless-teardown.md`

**Step 1: Write teardown documentation**

```markdown
# Serverless Infrastructure Teardown

This document describes how to safely decommission the serverless infrastructure after migrating to EC2.

## Pre-Teardown Checklist

- [ ] EC2 instance running and healthy
- [ ] All smoke tests passing
- [ ] DNS pointing to EC2
- [ ] At least 48 hours of stable operation
- [ ] Final backup from serverless infrastructure
- [ ] Users notified of maintenance window

## Teardown Steps

### 1. Disable Serverless Resources (Soft Delete)

First, disable without deleting to allow rollback:

```bash
# Disable backup Lambda schedule
aws events disable-rule --name cocktail-db-prod-BackupSchedule

# Disable analytics batch trigger
aws events disable-rule --name cocktail-db-prod-AnalyticsTrigger
```

### 2. Monitor for 24-48 Hours

Verify EC2 is handling all traffic correctly.

### 3. Delete CloudFormation Stack

Once confident, delete the serverless stack:

```bash
# First, empty S3 buckets (CloudFormation can't delete non-empty buckets)
aws s3 rm s3://cocktail-db-prod-website --recursive
aws s3 rm s3://cocktail-db-prod-analytics --recursive

# Delete the stack
aws cloudformation delete-stack --stack-name cocktail-db-prod

# Monitor deletion
aws cloudformation wait stack-delete-complete --stack-name cocktail-db-prod
```

### 4. Cleanup Orphaned Resources

Some resources may need manual cleanup:

- CloudWatch Log Groups
- ECR Repository images
- EFS file system (after final backup)
- Secrets Manager secrets (if used)

### 5. Update Monitoring

- Remove serverless-specific CloudWatch alarms
- Add EC2-specific monitoring
- Update PagerDuty/alerting integrations

## Rollback Procedure

If issues arise before teardown:

1. Update DNS back to CloudFront
2. Re-enable serverless schedules
3. Verify serverless stack is operational

## Cost Comparison

Document before/after costs:
- Lambda: $X/month
- EFS: $X/month
- NAT/VPC Endpoints: $X/month
- Batch: $X/month
- **Total Serverless**: $X/month

- EC2 (t4g.small): ~$12/month
- EBS (20GB gp3): ~$2/month
- **Total EC2**: ~$14/month
```

**Step 2: Commit**

```bash
git add docs/serverless-teardown.md
git commit -m "docs: add serverless teardown procedure"
```

---

## Execution Checklist

Use this checklist to track migration progress:

- [ ] Phase 1: Infrastructure Foundation
  - [ ] Task 1.1: Ansible project structure
  - [ ] Task 1.2: EC2 launch script
  - [ ] Task 1.3: Base provisioning playbook
  - [ ] Task 1.4: Database setup playbook

- [ ] Phase 2: Database Migration
  - [ ] Task 2.1: PostgreSQL schema
  - [ ] Task 2.2: Migration script
  - [ ] Task 2.3: Database abstraction layer

- [ ] Phase 3: API Containerization
  - [ ] Task 3.1: Production Dockerfile
  - [ ] Task 3.2: Docker Compose configuration
  - [ ] Task 3.3: Health check endpoint

- [ ] Phase 4: Reverse Proxy Configuration
  - [ ] Task 4.1: Caddy configuration
  - [ ] Task 4.2: Caddy deployment playbook

- [ ] Phase 5: Analytics Migration
  - [ ] Task 5.1: Analytics systemd service
  - [ ] Task 5.2: Update analytics for local execution
  - [ ] Task 5.3: On-demand analytics trigger

- [ ] Phase 6: Backup System
  - [ ] Task 6.1: PostgreSQL backup script
  - [ ] Task 6.2: Backup systemd timer

- [ ] Phase 7: Deployment Automation
  - [ ] Task 7.1: Full deployment playbook
  - [ ] Task 7.2: Deploy script

- [ ] Phase 8: DNS Cutover and Testing
  - [ ] Task 8.1: DNS update script
  - [ ] Task 8.2: Smoke test script

- [ ] Phase 9: Serverless Teardown
  - [ ] Task 9.1: Teardown documentation

---

## Notes

### Keep from Serverless Stack
- **Cognito User Pool**: Keep for authentication (no change needed)
- **S3 Backup Bucket**: Keep for backup storage
- **S3 Analytics Bucket**: Keep for analytics cache (EC2 writes here too)
- **Route53 Hosted Zone**: Keep, just update A record

### Remove from Serverless Stack
- Lambda functions (all)
- EFS file system
- VPC endpoints
- Batch compute environment
- API Gateway
- CloudFront distribution (replace with Caddy)

### SQLite vs PostgreSQL
The plan includes PostgreSQL migration, but this can be done separately. To keep SQLite initially:
1. Skip Phase 2 tasks 2.1-2.3
2. Use `DB_TYPE=sqlite` in environment
3. Mount SQLite database file into container
4. Migrate to PostgreSQL later as a separate project
