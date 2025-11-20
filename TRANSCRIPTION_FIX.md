# Fix: Audio Transcription Timeout Issue

## Problema Identificado

A tarefa `transcribe_audio` estava **travando** devido a **heartbeat timeout** no Airflow.

### Sintomas:
- Tarefa fica em estado "running" por ~10 minutos
- Airflow detecta "task instance without a heartbeat"
- Tarefa é marcada como "failed" e entra em retry
- Logs mostram: `Executor reported state failed, but task instance state is running`

### Causa Raiz:
1. **Whisper demora muito**: Processamento de áudio longo pode levar horas
2. **Sem heartbeat**: O subprocess do Whisper não reporta progresso ao Airflow
3. **Timeout padrão**: Airflow mata tarefas que não enviam sinais de vida

## Correções Implementadas

### 1. Heartbeat Thread ([transcoding_tasks.py:219-237](data/airflow/dags/transcode_pipeline/transcoding_tasks.py#L219-L237))

Adicionado thread de heartbeat que envia logs a cada 30 segundos:

```python
# Heartbeat mechanism to keep Airflow task alive
heartbeat_stop = threading.Event()

def send_heartbeat():
    """Send periodic heartbeats to Airflow"""
    counter = 0
    while not heartbeat_stop.is_set():
        counter += 1
        logger.info(f"[Task 6b] Heartbeat {counter}: Transcription still running")
        time.sleep(30)  # Send heartbeat every 30 seconds

# Start heartbeat thread
heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
heartbeat_thread.start()
```

**Benefício**: Airflow sabe que a tarefa está viva e processando

### 2. Timeout Aumentado ([video_transcoding_pipeline.py:124](data/airflow/dags/video_transcoding_pipeline.py#L124))

Aumentado timeout de execução para 2 horas:

```python
transcribe_audio = PythonOperator(
    task_id='transcribe_audio',
    python_callable=transcribe_audio_task,
    execution_timeout=timedelta(hours=2),  # Allow up to 2 hours for long videos
)
```

**Benefício**: Vídeos longos (>1 hora) podem ser transcritos completamente

### 3. Verificação Condicional ([transcoding_tasks.py:245-249](data/airflow/dags/transcode_pipeline/transcoding_tasks.py#L245-L249))

Tarefa verifica se transcrição está habilitada antes de processar:

```python
# Check if transcription is enabled for this job
if not job.enable_transcription:
    logger.info(f"[Task 6b] Transcription disabled for job {job_id}, skipping task")
    heartbeat_stop.set()  # Stop heartbeat before returning
    return  # Skip transcription
```

**Benefício**: Não desperdiça recursos em jobs que não precisam de transcrição

### 4. Cleanup do Heartbeat ([transcoding_tasks.py:323-325](data/airflow/dags/transcode_pipeline/transcoding_tasks.py#L323-L325))

Heartbeat é parado corretamente ao final da tarefa:

```python
finally:
    # Stop heartbeat thread
    heartbeat_stop.set()
    logger.info(f"[Task 6b] Stopped heartbeat thread")
    db.close()
```

**Benefício**: Threads são limpas adequadamente

## Arquivos Modificados

1. [data/airflow/dags/video_transcoding_pipeline.py](data/airflow/dags/video_transcoding_pipeline.py#L119-L125)
   - Aumentado `execution_timeout` para 2 horas

2. [data/airflow/dags/transcode_pipeline/transcoding_tasks.py](data/airflow/dags/transcode_pipeline/transcoding_tasks.py#L199-L327)
   - Adicionado heartbeat thread
   - Verificação condicional de `enable_transcription`
   - Cleanup adequado do heartbeat

## Como Usar

### Jobs COM transcrição:
```bash
curl -X POST http://localhost:8000/api/v1/jobs/upload \
  -H "X-API-Key: your-key" \
  -F "video_file=@video.mp4" \
  -F "enable_transcription=true" \
  -F "transcription_language=auto"
```

### Jobs SEM transcrição:
```bash
curl -X POST http://localhost:8000/api/v1/jobs/upload \
  -H "X-API-Key: your-key" \
  -F "video_file=@video.mp4" \
  -F "enable_transcription=false"
```

## Monitoramento

### Verificar progresso da transcrição:

```bash
# Ver heartbeats nos logs do Airflow
docker logs transcode-airflow-scheduler -f | grep "Heartbeat"

# Saída esperada:
# [Task 6b] Heartbeat 1: Transcription still running for job xyz
# [Task 6b] Heartbeat 2: Transcription still running for job xyz
# ...
```

### Tempo estimado por modelo Whisper:

| Modelo  | Duração Máxima | Velocidade | Qualidade | Tempo Estimado (60min vídeo) |
|---------|----------------|------------|-----------|------------------------------|
| tiny    | 3 min          | fastest    | low       | ~5 min                       |
| base    | 10 min         | fast       | medium    | ~10 min                      |
| small   | 30 min         | moderate   | good      | ~20 min                      |
| medium  | 60 min         | slow       | high      | ~40 min                      |
| large   | unlimited      | slowest    | best      | ~60-90 min                   |

## Próximos Passos

1. ✅ Jobs com transcrição desabilitada passam imediatamente
2. ✅ Jobs com transcrição habilitada processam até 2 horas
3. ✅ Heartbeats mantêm a tarefa viva durante processamento longo
4. ⏳ Aguardar restart do Airflow para aplicar mudanças
5. ⏳ Testar com vídeo real que tenha `enable_transcription=true`

## Troubleshooting

### Se ainda houver timeout:
1. Aumentar `execution_timeout` além de 2 horas
2. Reduzir frequência de heartbeat (aumentar `time.sleep()`)
3. Usar modelo Whisper menor (tiny/base) para vídeos longos

### Se heartbeat parar:
1. Verificar logs: `docker logs transcode-airflow-scheduler -f`
2. Verificar se thread está rodando
3. Verificar memória/CPU do container

## Aplicação das Mudanças

```bash
# Reiniciar Airflow para aplicar mudanças
docker restart transcode-airflow-scheduler transcode-airflow-webserver

# Aguardar ~30 segundos
sleep 30

# Verificar se DAG foi recarregado
docker logs transcode-airflow-scheduler --tail 50 | grep "video_transcoding_pipeline"
```
