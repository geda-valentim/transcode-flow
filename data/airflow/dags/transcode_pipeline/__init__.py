"""
Transcode Pipeline Module

Modular task definitions for the video transcoding DAG.
Each module contains related task functions.
"""
import sys
import os

# Add DAGs folder to Python path to allow imports
dags_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if dags_folder not in sys.path:
    sys.path.insert(0, dags_folder)

from transcode_pipeline.validation_tasks import (
    validate_video_task,
    generate_thumbnail_task
)
from transcode_pipeline.transcoding_tasks import (
    transcode_360p_task,
    transcode_720p_task,
    extract_audio_mp3_task
)
from transcode_pipeline.hls_tasks import (
    prepare_hls_task
)
from transcode_pipeline.storage_tasks import (
    upload_to_minio_task,
    upload_outputs_task
)
from transcode_pipeline.database_tasks import (
    update_database_task,
    cleanup_temp_files_task
)
from transcode_pipeline.notification_tasks import (
    send_notification_task
)

__all__ = [
    # Validation
    "validate_video_task",
    "generate_thumbnail_task",
    # Transcoding
    "transcode_360p_task",
    "transcode_720p_task",
    "extract_audio_mp3_task",
    # HLS
    "prepare_hls_task",
    # Storage
    "upload_to_minio_task",
    "upload_outputs_task",
    # Database
    "update_database_task",
    "cleanup_temp_files_task",
    # Notifications
    "send_notification_task",
]
