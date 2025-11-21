#!/bin/bash
set -e

echo "========================================"
echo "Airflow Initialization Starting"
echo "========================================"

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until PGPASSWORD=${POSTGRES_PASSWORD} psql -h ${POSTGRES_HOST:-postgres} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done
echo "PostgreSQL is up!"

# Check if database needs initialization
echo "Checking if Airflow database is initialized..."
if airflow db check 2>/dev/null; then
  echo "Airflow database already initialized"
else
  echo "Initializing Airflow database..."
  airflow db migrate
  echo "Database migration completed"
fi

# Create admin user if it doesn't exist
echo "Checking for admin user..."
if airflow users list 2>/dev/null | grep -q "${_AIRFLOW_WWW_USER_USERNAME:-admin}"; then
  echo "Admin user already exists"
else
  echo "Creating admin user..."
  airflow users create     --username "${_AIRFLOW_WWW_USER_USERNAME:-admin}"     --password "${_AIRFLOW_WWW_USER_PASSWORD:-admin}"     --firstname Admin     --lastname User     --role Admin     --email admin@example.com
  echo "Admin user created"
fi

# Run Alembic migrations for application database
echo "Running application database migrations..."
if [ -d "/opt/airflow/migrations" ]; then
  echo "Migrations directory found, running alembic..."
  cd /opt/airflow/migrations
  POSTGRES_USER=${POSTGRES_USER}   POSTGRES_PASSWORD=${POSTGRES_PASSWORD}   POSTGRES_HOST=${POSTGRES_HOST}   POSTGRES_PORT=5432   POSTGRES_DB=${POSTGRES_DB}   DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB}"   alembic upgrade head || echo "Warning: Alembic migrations failed or not configured"
else
  echo "No migrations directory found, skipping alembic"
fi

echo "========================================"
echo "Airflow Initialization Complete"
echo "========================================"
