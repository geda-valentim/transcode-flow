FROM apache/airflow:3.1.3-python3.11

USER root

# Install system dependencies (FFmpeg, FFprobe, Whisper dependencies)
RUN apt-get update && apt-get install -y     ffmpeg     libpq-dev     gcc     curl     git     && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /data/temp /opt/airflow/logs /opt/airflow/dags /opt/airflow/plugins

USER airflow

# Copy and install Python requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Set PYTHONPATH
ENV PYTHONPATH=/code:/opt/airflow/dags

USER root
