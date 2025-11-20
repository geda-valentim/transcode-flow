FROM python:3.11-slim

# Install system dependencies (FFmpeg, FFprobe, Whisper dependencies)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory to parent of app
WORKDIR /code

# Copy requirements file
COPY requirements.txt ./app/

# Install Python dependencies
RUN pip install --no-cache-dir -r app/requirements.txt

# Copy application code
COPY . ./app/

# Create temp directory
RUN mkdir -p /data/temp

# Set PYTHONPATH to include /code directory (parent of app)
ENV PYTHONPATH=/code

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application from /code directory
WORKDIR /code/app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
