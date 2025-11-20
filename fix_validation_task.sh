#!/bin/bash
# Script para corrigir o arquivo validation_tasks.py

TARGET_FILE="/home/transcode-flow/data/airflow/dags/transcode_pipeline/validation_tasks.py"

# Fazer backup
cp "$TARGET_FILE" "${TARGET_FILE}.bak"

# Aplicar correção usando sed
sed -i "s/if not validation_result\['valid'\]:/if not validation_result.is_valid:/" "$TARGET_FILE"
sed -i "s/job.error_message = validation_result.get('error', 'Video validation failed')/error_msgs = ', '.join(validation_result.errors) if validation_result.errors else 'Video validation failed'\n            job.error_message = error_msgs/" "$TARGET_FILE"
sed -i "s/video_info = validation_result\['info'\]/# Access validation result attributes directly/" "$TARGET_FILE"
sed -i "s/job.duration_seconds = video_info.get('duration')/job.duration_seconds = validation_result.duration_seconds/" "$TARGET_FILE"
sed -i "s/job.source_width = video_info.get('width')/job.source_width = validation_result.width/" "$TARGET_FILE"
sed -i "s/job.source_height = video_info.get('height')/job.source_height = validation_result.height/" "$TARGET_FILE"
sed -i "s/job.source_resolution = f\"{video_info.get('width')}x{video_info.get('height')}\"/job.source_resolution = validation_result.resolution or f\"{validation_result.width}x{validation_result.height}\"/" "$TARGET_FILE"
sed -i "s/job.file_size_bytes = video_info.get('size')/job.file_size_bytes = validation_result.size_bytes/" "$TARGET_FILE"

echo "Arquivo corrigido! Backup salvo em ${TARGET_FILE}.bak"
echo "Execute 'docker compose restart airflow-scheduler airflow-webserver' para aplicar as mudanças"
