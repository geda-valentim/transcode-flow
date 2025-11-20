#!/bin/bash
# Script para executar o teste da pipeline completa

# Configurar variáveis de ambiente para conexão local
export TEMP_DIR=/tmp/transcode-data
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/transcode_db"
export REDIS_URL="redis://localhost:6379/0"
export MINIO_HOST="localhost"
export MINIO_PORT=9000
export MINIO_ACCESS_KEY="admin"
export MINIO_SECRET_KEY="CHANGE_ME_MINIO_PASSWORD_123"
export MINIO_BUCKET="videos"
export MINIO_SECURE="False"
export SECRET_KEY="your-secret-key-here"
export FFPROBE_PATH="/usr/bin/ffprobe"
export FFMPEG_PATH="/usr/bin/ffmpeg"

# Executar teste
python3 /home/transcode-flow/test_pipeline.py
