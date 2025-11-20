FROM apache/airflow:3.1.3

USER root

# Install system dependencies for video processing and database client
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file with proper permissions
COPY --chown=airflow:root requirements.txt /opt/airflow/requirements.txt

USER airflow

# Install Python dependencies
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt
