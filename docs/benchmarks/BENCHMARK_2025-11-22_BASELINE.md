# Transcode Flow - Benchmark Report (Baseline)

**Date:** 2025-11-22
**Version:** Pre-decoupled transcription (coupled pipeline)
**Purpose:** Baseline metrics before transcription DAG optimization. Transcript stil part of the unique pipeline

---

## System Specifications

| Component | Specification |
|-----------|---------------|
| CPU | 13th Gen Intel Core i9-13900K |
| CPU Cores | 32 (logical) |
| RAM | 32 GB |
| Whisper Model | tiny (auto-selected) |
| FFmpeg Preset | medium |
| Environment | Docker (WSL2) |

---

## Task Duration Statistics

Based on **12 successful DAG runs** of `video_transcoding_pipeline`:

| Task | Executions | Avg (s) | Min (s) | Max (s) | Median (s) | P95 (s) | StdDev |
|------|------------|---------|---------|---------|------------|---------|--------|
| **transcribe_audio** | 9 | **96.29** | 0.14 | **549.58** | 0.18 | 447.66 | 195.55 |
| transcode_720p | 12 | 29.27 | 0.68 | 203.56 | 1.52 | 130.55 | 59.04 |
| transcode_360p | 12 | 24.44 | 0.44 | 155.83 | 0.96 | 109.33 | 46.75 |
| extract_audio_mp3 | 12 | 4.40 | 0.19 | 30.32 | 0.31 | 18.12 | 8.65 |
| generate_thumbnail | 12 | 1.26 | 0.53 | 2.51 | 1.14 | 2.35 | 0.68 |
| validate_video | 12 | 0.48 | 0.21 | 1.57 | 0.28 | 1.51 | 0.49 |
| upload_to_minio | 12 | 0.37 | 0.16 | 1.50 | 0.24 | 0.96 | 0.37 |
| prepare_hls_360p | 12 | 0.35 | 0.18 | 1.04 | 0.26 | 0.77 | 0.24 |
| upload_outputs | 9 | 0.33 | 0.20 | 0.80 | 0.25 | 0.68 | 0.20 |
| prepare_hls_720p | 12 | 0.31 | 0.18 | 0.72 | 0.22 | 0.66 | 0.18 |
| update_database | 9 | 0.14 | 0.12 | 0.19 | 0.14 | 0.18 | 0.02 |
| send_notification | 9 | 0.13 | 0.11 | 0.18 | 0.13 | 0.17 | 0.02 |
| cleanup_temp_files | 9 | 0.11 | 0.09 | 0.14 | 0.10 | 0.14 | 0.02 |

---

## Transcription Task Deep Dive

### Execution Details by Video

| Video File | Duration (s) | Processing (s) | Realtime Factor | Date |
|------------|--------------|----------------|-----------------|------|
| ABERTURA_5MINUTOS.mp4 | 317.46 | 549.58 | **0.58x** | 2025-11-21 |
| Projeto EBSERH - Depoimentos Aprovados.mp4 | 169.24 | 294.77 | **0.57x** | 2025-11-21 |
| test_video.mp4 | 5.00 | 0.14-0.25 | 20-36x | 2025-11-20/21 |

### Key Observations

1. **Realtime Factor for Long Videos**: ~0.57-0.58x (slower than realtime)
   - 5 min video (317s) = ~9 min to transcribe (549s)
   - 3 min video (169s) = ~5 min to transcribe (295s)

2. **Realtime Factor for Short Videos**: 20-36x (much faster than realtime)
   - 5 sec test video = 0.14-0.25s to transcribe

3. **High Variability**: StdDev (195.55s) > Mean (96.29s)
   - Indicates processing time is highly correlated with video duration
   - Model: Whisper `tiny` (fastest, lowest quality)

---

## Total Pipeline Duration

| Video | Duration (s) | Total Pipeline (s) | Ratio |
|-------|--------------|-------------------|-------|
| ABERTURA_5MINUTOS.mp4 | 317 | 556.78 | 1.76x |
| Projeto EBSERH - Depoimentos.mp4 | 169 | 299.89 | 1.77x |
| test_video.mp4 (optimized runs) | 5 | 5.63-7.55 | 1.1-1.5x |

**Note:** The total pipeline time is dominated by `transcribe_audio` for longer videos.

---

## Task Time Distribution (Percentage of Total)

For a typical long video (~300s duration):

```
transcribe_audio:  ████████████████████████████████████████████████  ~60%
transcode_720p:    ███████████████                                   ~18%
transcode_360p:    ████████████                                      ~15%
extract_audio_mp3: ███                                               ~4%
other tasks:       ██                                                ~3%
```

---

## Bottleneck Analysis

### Primary Bottleneck: `transcribe_audio`
- **Impact**: 60%+ of total pipeline time
- **Cause**: Whisper CPU inference is computationally intensive
- **Solution Implemented**: Decoupled transcription DAG (`transcription_pipeline`)

### Secondary Bottleneck: Video Transcoding (360p/720p)
- **Impact**: ~33% of total pipeline time
- **Current**: Sequential per resolution
- **Potential Optimization**: GPU acceleration (NVENC)

---

## Expected Improvements (Post-Decoupling)

With `transcription_pipeline` running separately:

| Metric | Before (Coupled) | After (Decoupled) | Improvement |
|--------|------------------|-------------------|-------------|
| Pipeline completion time (5 min video) | ~9-10 min | ~30-60 sec | **10-20x faster** |
| Transcription still completes | Yes | Yes (async) | Same quality |
| User gets video output | After transcription | Immediately | Better UX |

---

## Benchmark Commands

```sql
-- Task duration statistics
SELECT task_id,
       ROUND(AVG(EXTRACT(EPOCH FROM (end_date - start_date)))::numeric, 2) as avg_sec
FROM task_instance
WHERE dag_id = 'video_transcoding_pipeline' AND state = 'success'
GROUP BY task_id ORDER BY avg_sec DESC;

-- Transcription with video duration correlation
SELECT j.source_duration_seconds,
       EXTRACT(EPOCH FROM (ti.end_date - ti.start_date)) as processing_sec
FROM task_instance ti
JOIN dag_run dr ON ti.dag_id = dr.dag_id AND ti.run_id = dr.run_id
JOIN jobs j ON (dr.conf::json->>'job_id')::text = j.job_id
WHERE ti.task_id = 'transcribe_audio' AND ti.state = 'success';
```

---

## Next Steps

1. Run benchmark with decoupled `transcription_pipeline`
2. Test with larger video files (30+ min)
3. Compare Whisper models (tiny vs base vs small)
4. Test GPU acceleration for transcoding

---

*Generated: 2025-11-22 13:30 BRT*
