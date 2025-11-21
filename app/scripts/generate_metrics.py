#!/usr/bin/env python3
"""
Gera métricas do Prometheus para popular os dashboards.
"""
import time
import random
from app.metrics import *

print("\n🚀 Gerando métricas...\n")

# Jobs
for _ in range(15):
    record_job_created(api_key_prefix='tfk_test')
for _ in range(10):
    record_job_completed(api_key_prefix='tfk_test', duration_seconds=random.uniform(60, 600))
for _ in range(3):
    record_job_failed(api_key_prefix='tfk_test', error_type='test_error')

update_queue_metrics(queued_count=2, processing_count=2)
update_job_status_metrics({'pending': 2, 'processing': 2, 'completed': 10, 'failed': 3})

print("✅ Jobs: 15 created, 10 completed, 3 failed")

# Videos
for _ in range(10):
    for res in ['360p', '720p']:
        record_video_transcode(res, 'h264', random.uniform(30, 300), random.randint(5_000_000, 100_000_000))
    record_compression_ratio(random.uniform(1.5, 5.0))
    video_source_duration_seconds.observe(random.uniform(60, 600))
    video_source_size_bytes.observe(random.randint(10_000_000, 500_000_000))
    audio_extraction_duration_seconds.observe(random.uniform(5, 60))
    if random.random() > 0.3:
        transcription_duration_seconds.labels(model='whisper-base').observe(random.uniform(30, 180))
        transcription_word_count.observe(random.randint(100, 2000))
    thumbnail_generation_duration_seconds.observe(random.uniform(1, 10))

print("✅ Videos: 10 processed, 20 transcodings")

# Webhooks
for _ in range(12):
    record_webhook_sent('job.completed', random.random() > 0.2, random.uniform(0.1, 2.0))

print("✅ Webhooks: 12 sent")

# Storage
for _ in range(20):
    record_storage_operation(random.choice(['upload', 'download', 'delete']), random.random() > 0.15, random.uniform(0.5, 10.0))

print("✅ Storage: 20 operations")
print("\n✅ Concluído! Aguarde 30s e acesse o Grafana\n")
