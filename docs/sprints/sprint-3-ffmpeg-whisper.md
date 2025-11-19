# Sprint 3: FFmpeg & Whisper Integration (Week 4)

**Goal:** Implement video transcoding and transcription with FFmpeg and Whisper

**Duration:** 1 week
**Team Size:** 2-3 developers

---

## Tasks

- [ ] Optimize FFmpeg commands for 360p transcoding
- [ ] Optimize FFmpeg commands for 720p transcoding
- [ ] Implement HLS segmentation for streaming
- [ ] Implement MP3 audio extraction
- [ ] Set up Whisper in Docker container
- [ ] Implement Whisper transcription (TXT, SRT, VTT, JSON)
- [ ] Add automatic Whisper model selection based on duration
- [ ] Implement language detection and override
- [ ] Add FFmpeg progress tracking (percentage)
- [ ] Add Whisper progress tracking
- [ ] Implement resolution detection and conditional transcoding
- [ ] Add compression ratio calculation
- [ ] Add quality metrics (PSNR, SSIM - optional)
- [ ] Implement error handling for FFmpeg/Whisper failures
- [ ] Add timeout handling for long videos
- [ ] Optimize for multi-threading
- [ ] Test with various video formats
- [ ] Test transcription accuracy across languages
- [ ] Performance benchmarking

---

## Deliverables

- ✅ Working FFmpeg transcoding
- ✅ Working Whisper transcription
- ✅ HLS streaming segments generated
- ✅ Audio extraction working
- ✅ Subtitles generated (SRT, VTT)
- ✅ Progress tracking functional

---

## Acceptance Criteria

- [ ] 1080p video transcodes to 360p and 720p
- [ ] HLS playlists are valid and playable
- [ ] MP3 audio extracted correctly
- [ ] Transcription generates all 4 formats (TXT, SRT, VTT, JSON)
- [ ] Language auto-detection works correctly
- [ ] Processing time meets performance targets
- [ ] Handles various input formats (mp4, avi, mkv, etc.)
- [ ] Subtitles are properly timed and formatted

---

## Technical Details

### FFmpeg Optimizations

#### 360p Transcoding

```bash
ffmpeg -i input.mp4 \
  -vf "scale=-2:360" \
  -c:v libx264 \
  -preset medium \
  -crf 23 \
  -profile:v main \
  -level 3.1 \
  -movflags +faststart \
  -c:a aac \
  -b:a 96k \
  -ar 44100 \
  -threads 0 \
  -progress pipe:1 \
  output_360p.mp4
```

**Parameters Explained:**
- `scale=-2:360` - Scale to 360p height, maintain aspect ratio
- `preset medium` - Balance between speed and quality
- `crf 23` - Constant Rate Factor (18-28 range, 23 is good quality)
- `profile:v main` - H.264 profile for compatibility
- `movflags +faststart` - Enable streaming playback
- `threads 0` - Use all available CPU threads
- `progress pipe:1` - Output progress to stdout

#### 720p Transcoding

```bash
ffmpeg -i input.mp4 \
  -vf "scale=-2:720" \
  -c:v libx264 \
  -preset medium \
  -crf 22 \
  -profile:v high \
  -level 4.0 \
  -movflags +faststart \
  -c:a aac \
  -b:a 128k \
  -ar 48000 \
  -threads 0 \
  -progress pipe:1 \
  output_720p.mp4
```

#### HLS Segmentation

```bash
# For 360p
ffmpeg -i output_360p.mp4 \
  -codec: copy \
  -start_number 0 \
  -hls_time 10 \
  -hls_list_size 0 \
  -hls_segment_filename 'segment_%03d.ts' \
  -f hls \
  playlist_360p.m3u8

# For 720p
ffmpeg -i output_720p.mp4 \
  -codec: copy \
  -start_number 0 \
  -hls_time 10 \
  -hls_list_size 0 \
  -hls_segment_filename 'segment_%03d.ts' \
  -f hls \
  playlist_720p.m3u8
```

**HLS Parameters:**
- `hls_time 10` - 10-second segments (good balance)
- `hls_list_size 0` - Keep all segments in playlist
- `start_number 0` - Start segment numbering at 0

#### MP3 Audio Extraction

```bash
ffmpeg -i input.mp4 \
  -vn \
  -acodec libmp3lame \
  -b:a 192k \
  -ar 48000 \
  -q:a 2 \
  output.mp3
```

---

### Whisper Integration

#### Dockerfile for Whisper

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Whisper
RUN pip install --no-cache-dir openai-whisper

# Pre-download models
RUN whisper --model tiny --help
RUN whisper --model base --help
RUN whisper --model small --help

WORKDIR /app
```

#### Whisper Transcription Implementation

```python
import whisper
import os
from pathlib import Path

class WhisperTranscriber:
    def __init__(self):
        self.models = {}  # Cache loaded models

    def select_model(self, duration_seconds: float) -> str:
        """Auto-select Whisper model based on video duration"""
        if duration_seconds < 300:  # < 5 minutes
            return "tiny"
        elif duration_seconds < 1800:  # < 30 minutes
            return "base"
        elif duration_seconds < 3600:  # < 1 hour
            return "small"
        else:
            return "base"  # Use base for long videos (performance)

    def load_model(self, model_name: str):
        """Load and cache Whisper model"""
        if model_name not in self.models:
            self.models[model_name] = whisper.load_model(model_name)
        return self.models[model_name]

    def transcribe(
        self,
        audio_path: str,
        model_name: str = "base",
        language: str = None,
        output_dir: str = None
    ) -> dict:
        """
        Transcribe audio file using Whisper

        Returns dict with:
            - text: Full transcript
            - segments: Time-stamped segments
            - language: Detected language
            - word_timestamps: Word-level timestamps (if available)
        """
        # Load model
        model = self.load_model(model_name)

        # Transcribe with options
        options = {
            "verbose": True,
            "word_timestamps": True,
        }

        if language:
            options["language"] = language

        result = model.transcribe(audio_path, **options)

        # Save outputs
        if output_dir:
            self.save_outputs(result, output_dir, audio_path)

        return result

    def save_outputs(self, result: dict, output_dir: str, audio_path: str):
        """Save transcription in multiple formats"""
        os.makedirs(output_dir, exist_ok=True)
        base_name = Path(audio_path).stem

        # 1. Plain text (TXT)
        with open(f"{output_dir}/{base_name}.txt", "w", encoding="utf-8") as f:
            f.write(result["text"])

        # 2. SubRip (SRT)
        self.save_srt(result["segments"], f"{output_dir}/{base_name}.srt")

        # 3. WebVTT (VTT)
        self.save_vtt(result["segments"], f"{output_dir}/{base_name}.vtt")

        # 4. JSON (full data)
        import json
        with open(f"{output_dir}/{base_name}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    def save_srt(self, segments: list, output_path: str):
        """Save SubRip subtitle format"""
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, start=1):
                start = self.format_timestamp(segment["start"], srt=True)
                end = self.format_timestamp(segment["end"], srt=True)
                text = segment["text"].strip()

                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{text}\n\n")

    def save_vtt(self, segments: list, output_path: str):
        """Save WebVTT subtitle format"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")

            for segment in segments:
                start = self.format_timestamp(segment["start"])
                end = self.format_timestamp(segment["end"])
                text = segment["text"].strip()

                f.write(f"{start} --> {end}\n")
                f.write(f"{text}\n\n")

    def format_timestamp(self, seconds: float, srt: bool = False) -> str:
        """Format timestamp for subtitles"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        if srt:
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        else:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
```

#### Usage Example

```python
# In Airflow task
def transcribe_video_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    # Extract audio for Whisper (16kHz mono WAV)
    audio_path = f'/data/temp/{job_id}/audio.mp3'
    whisper_audio = f'/data/temp/{job_id}/audio_whisper.wav'

    subprocess.run([
        'ffmpeg', '-i', audio_path,
        '-ar', '16000',
        '-ac', '1',
        '-c:a', 'pcm_s16le',
        whisper_audio
    ], check=True)

    # Initialize transcriber
    transcriber = WhisperTranscriber()

    # Select model
    model_name = job.user_metadata.get('whisper_model') or \
                 transcriber.select_model(job.duration_seconds)

    # Get language
    language = job.user_metadata.get('transcription_language')

    # Transcribe
    output_dir = f'/data/temp/{job_id}/transcription'
    result = transcriber.transcribe(
        whisper_audio,
        model_name=model_name,
        language=language,
        output_dir=output_dir
    )

    # Update job in database
    word_count = len(result["text"].split())

    update_job(job_id, {
        'transcription_txt_path': f'{output_dir}/audio_whisper.txt',
        'transcription_srt_path': f'{output_dir}/audio_whisper.srt',
        'transcription_vtt_path': f'{output_dir}/audio_whisper.vtt',
        'transcription_json_path': f'{output_dir}/audio_whisper.json',
        'transcription_language': result.get('language', 'unknown'),
        'transcription_word_count': word_count,
        'whisper_model': model_name
    })

    return output_dir
```

---

### Progress Tracking

#### FFmpeg Progress Parser

```python
def parse_ffmpeg_progress(line: str) -> dict:
    """Parse FFmpeg progress output"""
    progress = {}

    for part in line.strip().split():
        if '=' in part:
            key, value = part.split('=', 1)
            progress[key] = value

    return progress

def run_ffmpeg_with_progress(cmd: list, job_id: str, task_name: str):
    """Run FFmpeg with real-time progress updates"""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    total_duration = get_job_duration(job_id)

    for line in process.stdout:
        if line.startswith('out_time_ms='):
            progress = parse_ffmpeg_progress(line)

            # Calculate percentage
            if 'out_time_ms' in progress:
                current_ms = int(progress['out_time_ms'])
                current_sec = current_ms / 1000000
                percent = min(int((current_sec / total_duration) * 100), 100)

                # Update job progress
                update_job_progress(job_id, task_name, percent)

    process.wait()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)
```

---

## Testing

### Test Cases

#### 1. Different Video Formats

```python
test_videos = [
    "sample.mp4",
    "sample.avi",
    "sample.mkv",
    "sample.mov",
    "sample.webm",
    "sample.flv"
]

for video in test_videos:
    job_id = create_job(video)
    assert wait_for_completion(job_id)
    assert verify_outputs(job_id, ['360p', '720p', 'audio'])
```

#### 2. Different Resolutions

```python
test_cases = [
    ("360p_video.mp4", ["360p"]),  # Only 360p output
    ("720p_video.mp4", ["360p", "720p"]),  # Both outputs
    ("1080p_video.mp4", ["360p", "720p"]),  # Both outputs
    ("4k_video.mp4", ["360p", "720p"]),  # Both outputs
]

for input_video, expected_outputs in test_cases:
    job_id = create_job(input_video)
    assert wait_for_completion(job_id)
    assert verify_outputs(job_id, expected_outputs)
```

#### 3. Transcription Accuracy

```python
test_languages = [
    ("english_video.mp4", "en"),
    ("portuguese_video.mp4", "pt"),
    ("spanish_video.mp4", "es"),
    ("french_video.mp4", "fr")
]

for video, expected_lang in test_languages:
    job_id = create_job(video)
    assert wait_for_completion(job_id)

    job = get_job(job_id)
    assert job.transcription_language == expected_lang

    # Verify all 4 formats exist
    assert os.path.exists(job.transcription_txt_path)
    assert os.path.exists(job.transcription_srt_path)
    assert os.path.exists(job.transcription_vtt_path)
    assert os.path.exists(job.transcription_json_path)
```

#### 4. HLS Playback

```python
def test_hls_playback():
    job_id = create_job("test_video.mp4")
    wait_for_completion(job_id)

    job = get_job(job_id)

    # Test 360p playlist
    playlist_360p = download_from_minio(job.output_hls_360p_path)
    assert "#EXTM3U" in playlist_360p
    assert ".ts" in playlist_360p

    # Test 720p playlist
    playlist_720p = download_from_minio(job.output_hls_720p_path)
    assert "#EXTM3U" in playlist_720p
    assert ".ts" in playlist_720p
```

---

## Performance Benchmarks

### Target Processing Times

| Video Duration | Resolution | Target Time | Max Time |
|----------------|-----------|-------------|----------|
| 1 minute | 360p | 30 seconds | 1 minute |
| 1 minute | 720p | 1 minute | 2 minutes |
| 10 minutes | 360p | 5 minutes | 8 minutes |
| 10 minutes | 720p | 10 minutes | 15 minutes |
| 1 hour | 360p | 30 minutes | 45 minutes |
| 1 hour | 720p | 60 minutes | 90 minutes |

### Whisper Performance

| Duration | Model | Target Time | Max Time |
|----------|-------|-------------|----------|
| 5 min | tiny | 1 min | 2 min |
| 5 min | base | 2 min | 4 min |
| 30 min | base | 10 min | 15 min |
| 1 hour | small | 25 min | 40 min |

---

## Notes

- **FFmpeg:** Use `-preset medium` for balance (fast/faster for speed, slow/slower for quality)
- **Whisper:** Models are cached after first load (saves time)
- **Progress:** Update database every 5% to avoid too many writes
- **Memory:** Each transcoding task can use up to 8GB RAM
- **Disk:** Ensure at least 3x video size free space for temp files

---

## Next Sprint

Sprint 4: Storage & File Management
