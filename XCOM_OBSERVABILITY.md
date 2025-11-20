# XCom Observability for Video Transcription

## Overview

Implementamos **observabilidade em tempo real** para a tarefa de transcrição de áudio usando **Airflow XCom** (cross-communication). XCom permite que tarefas compartilhem dados entre si e exponham métricas detalhadas de progresso.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                     Airflow DAG                                  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  transcribe_audio Task                                    │  │
│  │                                                            │  │
│  │  1. Push: transcription_status = "initializing"           │  │
│  │  2. Push: whisper_model_selected = "small"                │  │
│  │  3. Push: transcription_status = "extracting_audio"       │  │
│  │  4. Push: audio_file_size_mb = 4.5                        │  │
│  │  5. Push: transcription_status = "transcribing"           │  │
│  │  6. Push: transcription_status = "completed"              │  │
│  │  7. Push: transcription_text_length = 12345               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                       │
│                           │ XCom Values                           │
│                           ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Airflow XCom Backend (Database)                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI Observability Endpoints                 │
│                                                                   │
│  GET /api/v1/jobs/{job_id}/transcription/progress               │
│  GET /api/v1/jobs/{job_id}/metrics/detailed                     │
│  GET /api/v1/jobs/{job_id}/observability/summary                │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ JSON Response
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Client / Dashboard                           │
└─────────────────────────────────────────────────────────────────┘
```

## XCom Metrics Tracked

### Status Tracking

| XCom Key | Type | Description | Example Values |
|----------|------|-------------|----------------|
| `transcription_status` | string | Current processing status | `initializing`, `extracting_audio`, `transcribing`, `completed`, `failed` |
| `transcription_start_time` | ISO 8601 | When transcription task started | `2025-11-20T10:00:00Z` |
| `transcription_processing_start` | ISO 8601 | When Whisper processing started | `2025-11-20T10:01:00Z` |
| `transcription_processing_end` | ISO 8601 | When Whisper processing ended | `2025-11-20T10:15:00Z` |

### Whisper Model Metrics

| XCom Key | Type | Description | Example Values |
|----------|------|-------------|----------------|
| `whisper_model_selected` | string | Auto-selected Whisper model | `tiny`, `base`, `small`, `medium`, `large` |
| `whisper_model_speed` | string | Processing speed category | `fastest`, `fast`, `moderate`, `slow`, `slowest` |
| `whisper_model_quality` | string | Transcription quality level | `low`, `medium`, `good`, `high`, `best` |
| `video_duration_seconds` | float | Input video duration | `300.5` |

### Processing Metrics

| XCom Key | Type | Description | Example Values |
|----------|------|-------------|----------------|
| `audio_file_size_mb` | float | Extracted audio file size | `4.5` |
| `transcription_processing_duration_seconds` | float | Total processing time | `840.25` |
| `transcription_text_length` | int | Characters in transcribed text | `12345` |
| `transcription_segments_count` | int | Number of transcription segments | `87` |
| `transcription_detected_language` | string | Auto-detected language | `en`, `pt`, `es` |

### Output Data

| XCom Key | Type | Description |
|----------|------|-------------|
| `transcription_text` | string | Full transcribed text |
| `transcription_language` | string | Detected/specified language |
| `transcription_dir` | string | Output directory path |
| `transcription_files` | dict | Paths to all output formats |

### Error Tracking

| XCom Key | Type | Description |
|----------|------|-------------|
| `transcription_error` | string | Error message if failed |

## API Endpoints

### 1. Get Transcription Progress

```bash
GET /api/v1/jobs/{job_id}/transcription/progress
```

**Descrição**: Obtém progresso em tempo real da transcrição

**Resposta**:
```json
{
  "job_id": "abc123",
  "transcription_enabled": true,
  "status": "transcribing",
  "progress": {
    "status": "transcribing",
    "whisper_model": "small",
    "model_speed": "moderate",
    "model_quality": "good",
    "video_duration_seconds": 300,
    "audio_file_size_mb": 4.5,
    "processing_duration_seconds": 120,
    "estimated_time_remaining_seconds": 60
  },
  "metrics": {
    "start_time": "2025-11-20T10:00:00Z",
    "processing_start": "2025-11-20T10:01:00Z",
    "current_time": "2025-11-20T10:03:00Z"
  }
}
```

### 2. Get Detailed Job Metrics

```bash
GET /api/v1/jobs/{job_id}/metrics/detailed
```

**Descrição**: Métricas detalhadas de todas as tarefas do pipeline

**Resposta**:
```json
{
  "job_id": "abc123",
  "status": "processing",
  "source_video": {
    "filename": "video.mp4",
    "size_mb": 100.5,
    "duration_seconds": 300,
    "resolution": "1920x1080"
  },
  "processing": {
    "started_at": "2025-11-20T10:00:00Z",
    "current_task": "transcribe_audio",
    "current_task_progress": 50
  },
  "output": {
    "target_resolutions": ["360p", "720p"],
    "enable_hls": true,
    "enable_transcription": true
  }
}
```

### 3. Get Observability Summary

```bash
GET /api/v1/jobs/{job_id}/observability/summary
```

**Descrição**: Resumo de alto nível para dashboards

**Resposta**:
```json
{
  "job_id": "abc123",
  "status": "processing",
  "progress_percentage": 50,
  "current_task": "transcribe_audio",
  "quick_stats": {
    "source_file": "video.mp4 (100.5MB)",
    "duration": "300s",
    "created": "2025-11-20T09:00:00Z"
  },
  "features_enabled": {
    "transcoding": 2,
    "hls": true,
    "audio_extraction": true,
    "transcription": true
  }
}
```

## Código de Exemplo

### Monitorar Progresso em Python

```python
import requests
import time

def monitor_transcription(job_id, api_key):
    """Monitor transcription progress in real-time"""
    headers = {"X-API-Key": api_key}
    url = f"http://localhost:8000/api/v1/jobs/{job_id}/transcription/progress"

    while True:
        response = requests.get(url, headers=headers)
        data = response.json()

        status = data.get("progress", {}).get("status", "unknown")
        print(f"Status: {status}")

        if status == "completed":
            print("Transcription completed!")
            print(f"Language: {data['progress'].get('detected_language')}")
            print(f"Text length: {data['progress'].get('text_length')} chars")
            break
        elif status == "failed":
            print(f"Transcription failed: {data.get('error')}")
            break

        time.sleep(10)  # Check every 10 seconds

# Usage
monitor_transcription("job-123", "your-api-key")
```

### Dashboard em JavaScript

```javascript
async function updateTranscriptionDashboard(jobId) {
  const response = await fetch(
    `/api/v1/jobs/${jobId}/observability/summary`,
    {
      headers: { "X-API-Key": apiKey }
    }
  );

  const data = await response.json();

  // Update UI
  document.getElementById("status").textContent = data.status;
  document.getElementById("progress").style.width = `${data.progress_percentage}%`;
  document.getElementById("current-task").textContent = data.current_task;

  // If transcription is active, get detailed progress
  if (data.current_task === "transcribe_audio") {
    const transcriptionResponse = await fetch(
      `/api/v1/jobs/${jobId}/transcription/progress`,
      {
        headers: { "X-API-Key": apiKey }
      }
    );

    const transcriptionData = await transcriptionResponse.json();
    document.getElementById("whisper-model").textContent =
      transcriptionData.progress.whisper_model;
  }
}

// Poll every 5 seconds
setInterval(() => updateTranscriptionDashboard(jobId), 5000);
```

## Arquivos Modificados

### 1. [transcoding_tasks.py](data/airflow/dags/transcode_pipeline/transcoding_tasks.py)

Adicionados múltiplos `xcom_push()` em pontos estratégicos:

```python
# Status tracking
context['task_instance'].xcom_push(key='transcription_status', value='transcribing')

# Model selection
context['task_instance'].xcom_push(key='whisper_model_selected', value='small')
context['task_instance'].xcom_push(key='whisper_model_speed', value='moderate')

# Processing metrics
context['task_instance'].xcom_push(key='audio_file_size_mb', value=4.5)
context['task_instance'].xcom_push(key='transcription_processing_duration_seconds', value=120.5)

# Results
context['task_instance'].xcom_push(key='transcription_text_length', value=12345)
context['task_instance'].xcom_push(key='transcription_segments_count', value=87)
```

### 2. [observability.py](app/api/v1/endpoints/jobs/observability.py)

Novos endpoints criados:
- `GET /{job_id}/transcription/progress` - Progresso da transcrição
- `GET /{job_id}/metrics/detailed` - Métricas detalhadas
- `GET /{job_id}/observability/summary` - Resumo para dashboard

Funções helper:
- `get_airflow_xcom()` - Buscar valor específico do XCom
- `get_all_task_xcoms()` - Buscar todos os XComs de uma tarefa

## Heartbeat Thread

Além do XCom, mantemos um **heartbeat thread** que:
- Envia logs a cada 30 segundos
- Previne timeout do Airflow
- Mantém a tarefa "viva" durante processamento longo

```python
def send_heartbeat():
    """Send periodic heartbeats to Airflow"""
    counter = 0
    while not heartbeat_stop.is_set():
        counter += 1
        logger.info(f"[Task 6b] Heartbeat {counter}: Transcription still running")
        time.sleep(30)
```

## Fluxo de Estados

```
initializing
    ↓
extracting_audio
    ↓
transcribing
    ↓
completed / failed
```

## Métricas de Performance

### Estimativa de Tempo por Modelo

| Modelo | Vídeo 60min | Texto Gerado | Qualidade |
|--------|-------------|--------------|-----------|
| tiny   | ~5 min      | ~10,000 chars | Baixa |
| base   | ~10 min     | ~12,000 chars | Média |
| small  | ~20 min     | ~14,000 chars | Boa |
| medium | ~40 min     | ~15,000 chars | Alta |
| large  | ~90 min     | ~16,000 chars | Máxima |

## Troubleshooting

### XCom não disponível

**Problema**: Endpoint retorna "XCom data not available"

**Solução**:
1. Verificar se tarefa `transcribe_audio` foi executada
2. Confirmar que DAG run ID está armazenado em `job.metadata`
3. Verificar conectividade com Airflow API

### Métricas desatualizadas

**Problema**: Progresso não atualiza

**Solução**:
1. Verificar heartbeat logs: `docker logs transcode-airflow-scheduler -f | grep Heartbeat`
2. Confirmar que XCom push está funcionando
3. Verificar timeout do Airflow (deve ser 2 horas)

## Próximos Passos

1. ✅ XCom observability implementado
2. ✅ API endpoints criados
3. ✅ Documentação completa
4. ⏳ Armazenar `dag_run_id` no job metadata
5. ⏳ Criar dashboard web para visualização
6. ⏳ Adicionar webhooks para notificações de progresso

## Referências

- [Airflow XCom Documentation](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/xcoms.html)
- [Airflow REST API](https://airflow.apache.org/docs/apache-airflow/stable/stable-rest-api-ref.html)
- [Whisper Transcriber Service](app/services/whisper_transcriber.py)
- [Transcoding Tasks](data/airflow/dags/transcode_pipeline/transcoding_tasks.py)
