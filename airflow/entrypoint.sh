#!/bin/bash
set -e

echo "==================================="
echo "Transcode Flow - Airflow Init"
echo "==================================="

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-transcode_db}" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is ready!"

# Apply custom database migrations for jobs table
echo ""
echo "Applying Transcode Flow database migrations..."
if [ -f /opt/airflow/migrations/versions/002_jobs_table_aligned.sql ]; then
    PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-transcode_db}" -f /opt/airflow/migrations/versions/002_jobs_table_aligned.sql
    echo "✅ Jobs table migration applied successfully!"
else
    echo "⚠️  Migration file not found, skipping..."
    ls -la /opt/airflow/migrations/ || echo "Migrations directory not found"
fi

echo ""
echo "Running Airflow database migrations..."
airflow db migrate

# Create admin user if it doesn't exist
if [ -n "${_AIRFLOW_WWW_USER_USERNAME}" ] && [ -n "${_AIRFLOW_WWW_USER_PASSWORD}" ]; then
    echo ""
    echo "Creating Airflow admin user..."
    airflow users create \
        --username "${_AIRFLOW_WWW_USER_USERNAME}" \
        --firstname Admin \
        --lastname User \
        --role Admin \
        --email admin@example.com \
        --password "${_AIRFLOW_WWW_USER_PASSWORD}" 2>/dev/null || echo "User already exists"
fi

echo ""
echo "✅ Initialization complete!"
