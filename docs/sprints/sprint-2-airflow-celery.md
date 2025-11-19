# Sprint 2: Airflow DAG & Celery Workers (Week 3)

**Goal:** Implement the transcoding pipeline orchestration

**Duration:** 1 week
**Team Size:** 2 developers

---

## Tasks

- [ ] Set up Airflow webserver and scheduler
- [ ] Create video_transcoding_pipeline DAG
- [ ] Implement validate_video task
- [ ] Implement upload_to_minio task
- [ ] Implement generate_thumbnail task (5 auto-generated)
- [ ] Implement process_custom_thumbnail task
- [ ] Implement transcode_360p task
- [ ] Implement transcode_720p task
- [ ] Implement extract_audio_mp3 task
- [ ] Implement transcribe_video task (Whisper: TXT, SRT, VTT, JSON)
- [ ] Implement prepare_hls_360p task
- [ ] Implement prepare_hls_720p task
- [ ] Implement upload_outputs task
- [ ] Implement update_database task
- [ ] Implement cleanup_temp_files task
- [ ] Configure Celery workers (concurrency=8)
- [ ] Set up task retry policies
- [ ] Add progress tracking updates
- [ ] Deploy Flower for Celery monitoring

---

## Deliverables

- ✅ Complete Airflow DAG
- ✅ All tasks implemented
- ✅ Celery workers processing jobs
- ✅ Flower dashboard accessible

---

## Acceptance Criteria

- [ ] DAG visible in Airflow UI at http://localhost:8080
- [ ] Can trigger manual DAG runs
- [ ] Jobs process from upload to completion
- [ ] Progress updates visible in database
- [ ] Worker utilization visible in Flower at http://localhost:5555
- [ ] All 8 workers processing in parallel
- [ ] Task retry working correctly

---

## Technical Details

### DAG Structure

```python
# dags/video_transcoding_pipeline.py

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'transcode-flow',
    'depends_on_past': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
    'execution_timeout': timedelta(hours=4)
}

dag = DAG(
    'video_transcoding_pipeline',
    default_args=default_args,
    description='Complete video transcoding pipeline',
    schedule_interval=None,  # Triggered externally
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['video', 'transcoding'],
)

# Task 1: Validate video
validate_video = PythonOperator(
    task_id='validate_video',
    python_callable=validate_video_task,
    dag=dag,
)

# Task 2: Upload to MinIO
upload_to_minio = PythonOperator(
    task_id='upload_to_minio',
    python_callable=upload_to_minio_task,
    dag=dag,
)

# Task 3: Generate thumbnails
generate_thumbnail = PythonOperator(
    task_id='generate_thumbnail',
    python_callable=generate_thumbnail_task,
    dag=dag,
)

# Task 4: Transcode 360p
transcode_360p = PythonOperator(
    task_id='transcode_360p',
    python_callable=transcode_360p_task,
    dag=dag,
)

# Task 5: Transcode 720p
transcode_720p = PythonOperator(
    task_id='transcode_720p',
    python_callable=transcode_720p_task,
    dag=dag,
)

# Task 6: Extract audio
extract_audio_mp3 = PythonOperator(
    task_id='extract_audio_mp3',
    python_callable=extract_audio_task,
    dag=dag,
)

# Task 7: Transcribe video (Whisper)
transcribe_video = PythonOperator(
    task_id='transcribe_video',
    python_callable=transcribe_video_task,
    dag=dag,
)

# Task 8-9: Prepare HLS
prepare_hls_360p = PythonOperator(
    task_id='prepare_hls_360p',
    python_callable=prepare_hls_task,
    op_kwargs={'resolution': '360p'},
    dag=dag,
)

prepare_hls_720p = PythonOperator(
    task_id='prepare_hls_720p',
    python_callable=prepare_hls_task,
    op_kwargs={'resolution': '720p'},
    dag=dag,
)

# Task 10: Upload outputs
upload_outputs = PythonOperator(
    task_id='upload_outputs',
    python_callable=upload_outputs_task,
    dag=dag,
)

# Task 11: Update database
update_database = PythonOperator(
    task_id='update_database',
    python_callable=update_database_task,
    dag=dag,
)

# Task 12: Cleanup
cleanup_temp_files = PythonOperator(
    task_id='cleanup_temp_files',
    python_callable=cleanup_task,
    dag=dag,
)

# Task 13: Notification
send_notification = PythonOperator(
    task_id='send_notification',
    python_callable=send_notification_task,
    dag=dag,
)

# Dependencies
validate_video >> upload_to_minio >> generate_thumbnail
validate_video >> [transcode_360p, transcode_720p, extract_audio_mp3]
transcode_360p >> prepare_hls_360p >> upload_outputs
transcode_720p >> prepare_hls_720p >> upload_outputs
extract_audio_mp3 >> transcribe_video >> upload_outputs
upload_outputs >> update_database >> cleanup_temp_files >> send_notification
```

### Task Implementations

#### Task 1: Validate Video

```python
def validate_video_task(**context):
    job_id = context['dag_run'].conf['job_id']

    # Get job from database
    job = get_job(job_id)

    # Run FFprobe validation
    video_info = validate_video_file(job.source_path)

    # Update job with video info
    update_job(job_id, {
        'duration_seconds': video_info.duration,
        'source_resolution': video_info.resolution,
        'source_width': video_info.width,
        'source_height': video_info.height,
        'source_codec': video_info.codec,
        'status': 'validated'
    })

    return video_info
```

#### Task 2: Upload to MinIO

```python
def upload_to_minio_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    if job.source_type == 'filesystem':
        # Upload from filesystem to MinIO raw bucket
        minio_client.fput_object(
            bucket_name='videos',
            object_name=f'raw/{job_id}_original.mp4',
            file_path=job.source_path
        )

    # Already in MinIO if source_type == 'minio'
    return True
```

#### Task 3: Generate Thumbnails

```python
def generate_thumbnail_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    thumbnails = []
    positions = [0, 25, 50, 75, 100]  # Percentage positions

    for pos in positions:
        timestamp = (job.duration_seconds * pos) / 100

        # FFmpeg command to extract frame
        output_path = f'/data/temp/{job_id}/thumb_{pos}.jpg'

        cmd = [
            'ffmpeg', '-ss', str(timestamp),
            '-i', job.source_path,
            '-vframes', '1',
            '-q:v', '2',
            output_path
        ]

        subprocess.run(cmd, check=True)
        thumbnails.append(output_path)

    # Process custom thumbnail if provided
    if job.thumbnail_custom_path:
        # Copy and resize custom thumbnail
        process_custom_thumbnail(job_id, job.thumbnail_custom_path)

    return thumbnails
```

#### Task 4-5: Transcoding Tasks

```python
def transcode_360p_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    # Check if source resolution allows 360p
    if job.source_height < 360:
        return None  # Skip

    output_path = f'/data/temp/{job_id}/video_360p.mp4'

    # Update progress
    update_job_progress(job_id, task='transcode_360p', percent=0)

    # FFmpeg command with progress tracking
    cmd = [
        'ffmpeg', '-i', job.source_path,
        '-vf', 'scale=-2:360',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
        '-profile:v', 'main', '-level', '3.1',
        '-movflags', '+faststart',
        '-c:a', 'aac', '-b:a', '96k', '-ar', '44100',
        '-progress', 'pipe:1',  # Progress to stdout
        output_path
    ]

    # Run with progress tracking
    start_time = time.time()
    run_ffmpeg_with_progress(cmd, job_id, 'transcode_360p')
    end_time = time.time()

    # Update job with metrics
    update_job(job_id, {
        'output_360p_path': output_path,
        'output_360p_size_bytes': os.path.getsize(output_path),
        'transcode_360p_time_seconds': int(end_time - start_time),
        'compression_ratio_360p': calculate_compression_ratio(job, output_path)
    })

    return output_path

def transcode_720p_task(**context):
    # Similar to 360p but with 720p settings
    ...
```

#### Task 6: Extract Audio

```python
def extract_audio_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    output_path = f'/data/temp/{job_id}/audio.mp3'

    cmd = [
        'ffmpeg', '-i', job.source_path,
        '-vn', '-acodec', 'libmp3lame',
        '-b:a', '192k', '-ar', '48000',
        output_path
    ]

    start_time = time.time()
    subprocess.run(cmd, check=True)
    end_time = time.time()

    update_job(job_id, {
        'output_audio_path': output_path,
        'output_audio_size_bytes': os.path.getsize(output_path),
        'audio_extraction_time_seconds': int(end_time - start_time)
    })

    return output_path
```

#### Task 7: Transcribe Video (Whisper)

```python
def transcribe_video_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    # Get audio file from previous task
    audio_path = f'/data/temp/{job_id}/audio.mp3'

    # Extract audio for Whisper (16kHz mono WAV)
    whisper_audio = f'/data/temp/{job_id}/audio_whisper.wav'
    cmd = [
        'ffmpeg', '-i', audio_path,
        '-ar', '16000', '-ac', '1',
        '-c:a', 'pcm_s16le',
        whisper_audio
    ]
    subprocess.run(cmd, check=True)

    # Select Whisper model based on duration
    model = select_whisper_model(job.duration_seconds)

    # Run Whisper transcription
    output_dir = f'/data/temp/{job_id}/transcription'
    os.makedirs(output_dir, exist_ok=True)

    start_time = time.time()

    cmd = [
        'whisper', whisper_audio,
        '--model', model,
        '--language', job.user_metadata.get('transcription_language', 'auto'),
        '--output_format', 'all',  # txt, srt, vtt, json
        '--output_dir', output_dir
    ]

    subprocess.run(cmd, check=True)
    end_time = time.time()

    # Count words in transcript
    with open(f'{output_dir}/audio_whisper.txt', 'r') as f:
        word_count = len(f.read().split())

    # Detect language from JSON output
    with open(f'{output_dir}/audio_whisper.json', 'r') as f:
        whisper_data = json.load(f)
        detected_language = whisper_data.get('language', 'unknown')

    update_job(job_id, {
        'transcription_txt_path': f'{output_dir}/audio_whisper.txt',
        'transcription_srt_path': f'{output_dir}/audio_whisper.srt',
        'transcription_vtt_path': f'{output_dir}/audio_whisper.vtt',
        'transcription_json_path': f'{output_dir}/audio_whisper.json',
        'transcription_time_seconds': int(end_time - start_time),
        'transcription_language': detected_language,
        'transcription_word_count': word_count,
        'whisper_model': model
    })

    return output_dir

def select_whisper_model(duration_seconds):
    if duration_seconds < 300:  # < 5 minutes
        return "tiny"
    elif duration_seconds < 1800:  # < 30 minutes
        return "base"
    elif duration_seconds < 3600:  # < 1 hour
        return "small"
    else:
        return "base"  # Large videos use base for performance
```

#### Task 8-9: Prepare HLS

```python
def prepare_hls_task(resolution, **context):
    job_id = context['dag_run'].conf['job_id']

    input_path = f'/data/temp/{job_id}/video_{resolution}.mp4'
    output_dir = f'/data/temp/{job_id}/{resolution}/segments'
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        'ffmpeg', '-i', input_path,
        '-codec:', 'copy',
        '-start_number', '0',
        '-hls_time', '10',
        '-hls_list_size', '0',
        '-f', 'hls',
        f'{output_dir}/playlist.m3u8'
    ]

    subprocess.run(cmd, check=True)

    # Count segments
    segment_count = len([f for f in os.listdir(output_dir) if f.endswith('.ts')])
    segments_size = sum(os.path.getsize(f'{output_dir}/{f}')
                       for f in os.listdir(output_dir) if f.endswith('.ts'))

    update_job(job_id, {
        f'output_hls_{resolution}_path': f'{output_dir}/playlist.m3u8',
        f'segments_{resolution}_count': segment_count,
        f'segments_{resolution}_size_bytes': segments_size
    })

    return output_dir
```

#### Task 10: Upload Outputs

```python
def upload_outputs_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    # Upload all outputs to MinIO
    base_path = f'processed/{job_id}'

    # Upload transcoded videos
    if job.output_360p_path:
        minio_client.fput_object('videos', f'{base_path}/360p/video_360p.mp4', job.output_360p_path)

    if job.output_720p_path:
        minio_client.fput_object('videos', f'{base_path}/720p/video_720p.mp4', job.output_720p_path)

    # Upload audio
    minio_client.fput_object('videos', f'{base_path}/audio/audio.mp3', job.output_audio_path)

    # Upload transcription files
    upload_directory_to_minio(f'/data/temp/{job_id}/transcription', f'{base_path}/transcription')

    # Upload HLS segments
    if job.output_hls_360p_path:
        upload_directory_to_minio(f'/data/temp/{job_id}/360p/segments', f'{base_path}/360p/segments')

    if job.output_hls_720p_path:
        upload_directory_to_minio(f'/data/temp/{job_id}/720p/segments', f'{base_path}/720p/segments')

    # Upload thumbnails
    upload_directory_to_minio(f'/data/temp/{job_id}/thumbnails', f'{base_path}/thumbnails')

    # Generate and upload metadata.json
    metadata = generate_metadata_json(job)
    minio_client.put_object(
        'videos',
        f'{base_path}/metadata.json',
        io.BytesIO(json.dumps(metadata, indent=2).encode()),
        len(json.dumps(metadata, indent=2))
    )

    return True
```

---

## Celery Configuration

```python
# celery_config.py

CELERY_CONFIG = {
    'broker_url': 'redis://redis:6379/0',
    'result_backend': 'db+postgresql://airflow:password@postgres:5432/airflow',
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'UTC',
    'worker_concurrency': 8,  # Match CPU threads
    'worker_prefetch_multiplier': 1,
    'task_acks_late': True,
    'task_reject_on_worker_lost': True,
    'task_time_limit': 14400,  # 4 hours
    'task_soft_time_limit': 13500  # 3h45m
}
```

---

## Testing

- [ ] Test DAG with small video (< 1 minute)
- [ ] Test DAG with medium video (5-10 minutes)
- [ ] Test with different resolutions (360p, 720p, 1080p, 4K)
- [ ] Test custom thumbnail upload
- [ ] Test Whisper transcription in multiple languages
- [ ] Test task retry on failure
- [ ] Test parallel processing (8 workers)
- [ ] Test cleanup of temp files

---

## Next Sprint

Sprint 3: FFmpeg & Whisper Integration
