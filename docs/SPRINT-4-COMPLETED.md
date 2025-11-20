# SPRINT 4: STORAGE & FILE MANAGEMENT - COMPLETO

**Data de Conclusão:** 2025-01-19
**Status:** ✅ 100% Implementado

---

## SUMÁRIO EXECUTIVO

Sprint 4 implementa gerenciamento completo de armazenamento para o TranscodeFlow, incluindo políticas de ciclo de vida, quotas, URLs presigned para downloads seguros, detecção de duplicatas e limpeza automática.

**Principais Entregas:**
- ✅ Lifecycle Policies do MinIO
- ✅ Storage Quota Management
- ✅ Presigned URL Generator
- ✅ Duplicate Detection
- ✅ Storage Cleanup Service
- ✅ DAG de Cleanup Automático
- ✅ API Endpoints de Download

---

## 1. LIFECYCLE POLICIES DO MINIO

### Implementação

**Arquivo:** [`/app/storage/lifecycle.py`](/app/storage/lifecycle.py)

### Features Implementadas

```python
class LifecyclePolicyManager:
    """
    Gerenciador de políticas de ciclo de vida do MinIO

    Features:
    - Deleção automática de arquivos temporários
    - Políticas baseadas em idade
    - Regras por prefixo (temp/, failed/, completed/)
    - Validação e deployment de políticas
    - Monitoramento de status
    """
```

### Políticas Padrão

| Nome | Prefixo | Retenção | Descrição |
|------|---------|----------|-----------|
| `cleanup-temp-files` | `temp/` | 1 dia | Remove arquivos temporários |
| `cleanup-failed-jobs` | `failed/` | 7 dias | Remove outputs de jobs falhados |
| `cleanup-thumbnails` | `thumbnails/` | 30 dias | Remove thumbnails antigos |

### Uso

```python
from storage.lifecycle import LifecyclePolicyManager, create_default_lifecycle_policies

# Criar manager
manager = LifecyclePolicyManager(minio_client, bucket_name)

# Aplicar políticas padrão
manager.apply_lifecycle_policies()

# Verificar status
status = manager.get_policy_status()

# Adicionar política customizada
custom_policy = RetentionPolicy(
    name="cleanup-old-videos",
    prefix="archive/",
    days=90,
    description="Remove vídeos arquivados após 90 dias"
)
manager.add_policy(custom_policy)
```

---

## 2. STORAGE QUOTA MANAGEMENT

### Implementação

**Arquivo:** [`/app/storage/quota.py`](/app/storage/quota.py)

### Features Implementadas

```python
class StorageQuotaManager:
    """
    Gerenciamento de quotas de armazenamento

    Features:
    - Quotas por usuário
    - Quotas por bucket
    - Tracking de uso em tempo real
    - Notificações de warning (80% threshold)
    - Enforcement antes de upload
    - Analytics de storage
    """
```

### Funcionalidades

#### Definir Quota
```python
manager = StorageQuotaManager(minio_client, bucket_name)

# Definir quota de 100GB para usuário
quota = manager.set_quota(
    entity_id="user123",
    entity_type="user",
    quota_gb=100.0,
    warning_threshold=0.8  # 80%
)
```

#### Verificar Quota Antes de Upload
```python
# Verificar se upload é permitido
check = manager.check_quota("user123", additional_bytes=500_000_000)

if check['would_exceed']:
    print(f"Quota excedida! Usado: {check['used_gb']}GB de {check['quota_gb']}GB")
else:
    print(f"Upload permitido. Espaço disponível: {check['available_gb']}GB")
```

#### Enforçar Quota
```python
from storage.quota import QuotaExceededError

try:
    manager.enforce_quota("user123", file_size=1_000_000_000)
    # Upload permitido
except QuotaExceededError as e:
    # Quota excedida
    print(f"Erro: {e}")
```

#### Relatório de Uso
```python
# Relatório individual
report = manager.get_usage_report(entity_id="user123")
print(f"Uso: {report['quota']['usage_percentage']:.1f}%")

# Relatório global
global_report = manager.get_usage_report()
print(f"Total de entidades: {global_report['total_entities']}")
print(f"Quotas excedidas: {global_report['exceeded_count']}")
```

---

## 3. PRESIGNED URL GENERATOR

### Implementação

**Arquivo:** [`/app/storage/presigned.py`](/app/storage/presigned.py)

### Features Implementadas

```python
class PresignedURLGenerator:
    """
    Gerador de URLs presigned para acesso seguro sem autenticação

    Features:
    - Download URLs (GET)
    - Upload URLs (PUT)
    - Expiração configurável (1h - 7 dias)
    - Headers customizados de response
    - Suporte para HLS manifests
    - Batch URL generation
    """
```

### Funcionalidades

#### URL de Download
```python
generator = PresignedURLGenerator(minio_client, bucket_name)

# URL simples de download
url = generator.generate_download_url(
    'videos/abc123/output.mp4',
    expires=timedelta(hours=2)
)

# URL com attachment (forçar download)
url = generator.get_direct_download_url(
    'videos/abc123/output.mp4',
    filename='video.mp4',
    expires=timedelta(hours=1)
)

# URL para visualização inline (player)
url = generator.get_inline_view_url(
    'videos/abc123/output.mp4',
    content_type='video/mp4',
    expires=timedelta(hours=24)
)
```

#### URL de Upload
```python
# Gerar URL para upload direto ao MinIO
upload_url = generator.generate_upload_url(
    'uploads/user123/video.mp4',
    expires=timedelta(minutes=30)
)
# Cliente pode fazer PUT direto nessa URL
```

#### Batch URLs (Todos os outputs de um job)
```python
urls = generator.generate_video_outputs_urls('job-abc123')

# Retorna URLs para:
# - 360p_video, 720p_video
# - audio (MP3)
# - thumbnail (JPG)
# - hls_360p_playlist, hls_720p_playlist
# - transcription_txt, transcription_srt, transcription_vtt, transcription_json
```

#### HLS Streaming URLs
```python
hls_urls = generator.generate_hls_manifest_urls(
    job_id='abc123',
    resolution='720p',
    expires=timedelta(hours=2)
)

# Retorna:
# - playlist: URL do playlist.m3u8
# - segments: {segment0.ts: URL, segment1.ts: URL, ...}
```

---

## 4. DUPLICATE DETECTION

### Implementação

**Arquivo:** [`/app/storage/deduplication.py`](/app/storage/deduplication.py)

### Features Implementadas

```python
class DuplicateDetector:
    """
    Detecção de duplicatas usando SHA-256 hashing

    Features:
    - Hash SHA-256 de arquivos
    - Database in-memory de hashes
    - Detecção antes de upload
    - Cálculo de espaço desperdiçado
    - Batch scanning
    - Remoção automática de duplicatas
    """
```

### Funcionalidades

#### Scan Completo do Bucket
```python
detector = DuplicateDetector(minio_client, bucket_name)

# Scan completo
results = detector.scan_bucket(recursive=True)

print(f"Total de arquivos: {results['total_files']}")
print(f"Hashes únicos: {results['unique_hashes']}")
print(f"Duplicatas encontradas: {results['total_duplicates']}")
print(f"Espaço desperdiçado: {results['wasted_space_gb']:.2f}GB")
print(f"Economia potencial: {results['savings_percentage']:.1f}%")
```

#### Verificar Duplicata Antes de Upload
```python
# Verificar se arquivo já existe
duplicate = detector.check_duplicate('/local/path/video.mp4')

if duplicate:
    print(f"Duplicata encontrada: {duplicate.object_name}")
    print("Não fazer upload, usar arquivo existente")
else:
    print("Arquivo único, pode fazer upload")
```

#### Remover Duplicatas
```python
# Dry-run (apenas simular)
result = detector.remove_duplicates(dry_run=True, keep_strategy='oldest')
print(f"Seriam deletados: {result['files_deleted']} arquivos")
print(f"Espaço liberado: {result['space_freed_gb']:.2f}GB")

# Executar remoção real
result = detector.remove_duplicates(dry_run=False, keep_strategy='oldest')
print(f"Deletados: {result['files_deleted']} arquivos")
```

#### Relatório de Duplicatas
```python
report = detector.get_duplicate_report()
print(report)

# Saída:
# ============================================================
# DUPLICATE DETECTION REPORT
# ============================================================
# Total files scanned: 1523
# Unique files: 1342
# Duplicate groups: 45
# Total duplicates: 181
# Wasted space: 12.45 GB
# ============================================================
```

---

## 5. STORAGE CLEANUP SERVICE

### Implementação

**Arquivo:** [`/app/storage/cleanup.py`](/app/storage/cleanup.py)

### Features Implementadas

```python
class StorageCleanupService:
    """
    Serviço de limpeza de storage

    Features:
    - Limpeza baseada em idade
    - Múltiplas regras de cleanup
    - Dry-run mode para testes
    - Relatórios detalhados
    - Cleanup de jobs falhados específicos
    - Detecção de arquivos órfãos
    """
```

### Regras Padrão

| Nome | Prefixo | Idade Máxima | Descrição |
|------|---------|--------------|-----------|
| `cleanup-temp-files` | `temp/` | 1 dia | Remove arquivos temporários |
| `cleanup-failed-jobs` | `failed/` | 7 dias | Remove outputs de jobs falhados |
| `cleanup-old-thumbnails` | `thumbnails/` | 30 dias | Remove thumbnails antigos |

### Funcionalidades

#### Cleanup Completo
```python
service = StorageCleanupService(minio_client, bucket_name)

# Dry-run (testar sem deletar)
results = service.cleanup_all(dry_run=True)

for result in results:
    print(f"{result.rule_name}: {result.files_deleted} arquivos, {result.space_freed_mb:.2f}MB")

# Executar cleanup real
results = service.cleanup_all(dry_run=False)
```

#### Cleanup de Jobs Falhados Específicos
```python
# Limpar jobs específicos
failed_job_ids = ['job-123', 'job-456', 'job-789']

result = service.cleanup_failed_jobs(failed_job_ids, dry_run=False)
print(f"Jobs limpos: {result['jobs_cleaned']}")
print(f"Arquivos deletados: {result['files_deleted']}")
print(f"Espaço liberado: {result['space_freed_mb']:.2f}MB")
```

#### Cleanup de Jobs Antigos
```python
# Limpar jobs completos com mais de 30 dias
result = service.cleanup_old_jobs(max_age_days=30, dry_run=False)
print(f"Jobs antigos limpos: {result.files_deleted} arquivos")
```

#### Detectar e Limpar Arquivos Órfãos
```python
# Obter IDs válidos do banco de dados
valid_job_ids = get_all_job_ids_from_database()

# Encontrar arquivos órfãos (sem job correspondente no BD)
orphaned = service.find_orphaned_files(valid_job_ids)
print(f"Arquivos órfãos encontrados: {len(orphaned)}")

# Limpar órfãos
result = service.cleanup_orphaned_files(orphaned, dry_run=False)
print(f"Órfãos removidos: {result['files_deleted']}")
print(f"Espaço liberado: {result['space_freed_mb']:.2f}MB")
```

---

## 6. DAG DE CLEANUP AUTOMÁTICO

### Implementação

**Arquivo:** [`/data/airflow/dags/storage_cleanup_pipeline.py`](/data/airflow/dags/storage_cleanup_pipeline.py)

### Configuração

```python
dag = DAG(
    'storage_cleanup_pipeline',
    schedule_interval='0 2 * * *',  # Roda diariamente às 2h AM
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['storage', 'cleanup', 'maintenance'],
)
```

### Tasks do DAG

#### 1. cleanup_temp_files
Remove arquivos temporários com mais de 1 dia:
- Prefixo: `temp/`
- Max age: 1 dia
- Executa em paralelo com outras tasks

#### 2. cleanup_failed_jobs
Remove outputs de jobs falhados com mais de 7 dias:
- Prefixo: `failed/`
- Max age: 7 dias
- Executa em paralelo com outras tasks

#### 3. cleanup_old_thumbnails
Remove thumbnails com mais de 30 dias:
- Prefixo: `thumbnails/`
- Max age: 30 dias
- Executa em paralelo com outras tasks

#### 4. scan_for_duplicates
Escaneia o bucket inteiro para detectar duplicatas:
- Calcula hashes SHA-256
- Identifica grupos de duplicatas
- Reporta espaço desperdiçado
- **Nota:** Apenas detecta, não remove (ação manual requerida)

#### 5. generate_cleanup_report
Gera relatório consolidado:
- Total de arquivos deletados
- Espaço liberado
- Duplicatas detectadas
- Logs no Airflow

### Fluxo do DAG

```
cleanup_temp_files ────┐
cleanup_failed_jobs ───┼──> scan_for_duplicates ──> generate_cleanup_report
cleanup_old_thumbnails ┘
```

### Exemplo de Relatório Gerado

```
============================================================
STORAGE CLEANUP REPORT
Date: 2025-01-19 02:00:00
============================================================

CLEANUP SUMMARY:
  Total files deleted: 1,523
  Total space freed: 12,456.78 MB (12.17 GB)

BREAKDOWN:
  Temp files: 1,234 files, 8,900.12 MB
  Failed jobs: 156 files, 2,345.67 MB
  Thumbnails: 133 files, 1,210.99 MB

DUPLICATE FILES:
  Duplicate groups: 45
  Total duplicates: 181
  Wasted space: 3.4567 GB
============================================================
```

---

## 7. API ENDPOINTS DE DOWNLOAD

### Implementação

**Arquivo:** [`/app/api/downloads.py`](/app/api/downloads.py)

### Endpoints Implementados

#### GET `/downloads/job/{job_id}/outputs`
Retorna URLs presigned para todos os outputs de um job.

**Query Params:**
- `expires_hours`: Expiração (1-24h, default=1)

**Response:**
```json
{
  "job_id": "abc123",
  "urls": {
    "360p_video": "https://minio:9000/...",
    "720p_video": "https://minio:9000/...",
    "audio": "https://minio:9000/...",
    "thumbnail": "https://minio:9000/...",
    "hls_360p_playlist": "https://minio:9000/...",
    "hls_720p_playlist": "https://minio:9000/...",
    "transcription_txt": "https://minio:9000/...",
    "transcription_srt": "https://minio:9000/...",
    "transcription_vtt": "https://minio:9000/...",
    "transcription_json": "https://minio:9000/..."
  }
}
```

#### GET `/downloads/job/{job_id}/video/{resolution}`
Retorna URL presigned para download de vídeo específico.

**Path Params:**
- `job_id`: ID do job
- `resolution`: `360p` ou `720p`

**Query Params:**
- `expires_hours`: Expiração (1-24h, default=1)
- `download`: `true` para forçar download, `false` para visualização inline (default=false)

**Response:**
```json
{
  "url": "https://minio:9000/...",
  "object_name": "jobs/abc123/outputs/720p.mp4",
  "expires_in_seconds": 3600,
  "created_at": "2025-01-19T10:00:00Z",
  "expires_at": "2025-01-19T11:00:00Z"
}
```

#### GET `/downloads/job/{job_id}/audio`
Retorna URL presigned para download de áudio (MP3).

**Path Params:**
- `job_id`: ID do job

**Query Params:**
- `expires_hours`: Expiração (1-24h, default=1)

#### GET `/downloads/job/{job_id}/thumbnail`
Retorna URL presigned para thumbnail.

**Path Params:**
- `job_id`: ID do job

**Query Params:**
- `expires_hours`: Expiração (1-24h, default=1)

#### GET `/downloads/job/{job_id}/transcription/{format}`
Retorna URL presigned para arquivo de transcrição.

**Path Params:**
- `job_id`: ID do job
- `format`: `txt`, `srt`, `vtt`, ou `json`

**Query Params:**
- `expires_hours`: Expiração (1-24h, default=1)

#### GET `/downloads/job/{job_id}/hls/{resolution}`
Retorna URLs presigned para HLS streaming (playlist + segments).

**Path Params:**
- `job_id`: ID do job
- `resolution`: `360p` ou `720p`

**Query Params:**
- `expires_hours`: Expiração (1-24h, default=2)

**Response:**
```json
{
  "job_id": "abc123",
  "resolution": "720p",
  "playlist_url": "https://minio:9000/.../playlist.m3u8",
  "segments": {
    "segment0.ts": "https://minio:9000/.../segment0.ts",
    "segment1.ts": "https://minio:9000/.../segment1.ts",
    ...
  }
}
```

#### GET `/downloads/object`
Endpoint genérico para download de qualquer objeto.

**Query Params:**
- `object_name` (required): Path completo do objeto
- `expires_hours`: Expiração (1-24h, default=1)
- `filename`: Nome customizado para download (optional)

---

## ARQUIVOS CRIADOS/MODIFICADOS

### Novos Arquivos

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `/app/storage/__init__.py` | 45 | Module exports |
| `/app/storage/lifecycle.py` | 352 | Lifecycle policy manager |
| `/app/storage/quota.py` | 428 | Storage quota management |
| `/app/storage/presigned.py` | 442 | Presigned URL generator |
| `/app/storage/deduplication.py` | 398 | Duplicate detection |
| `/app/storage/cleanup.py` | 446 | Storage cleanup service |
| `/data/airflow/dags/storage_cleanup_pipeline.py` | 354 | Cleanup DAG |
| `/app/api/downloads.py` | 447 | Download API endpoints |

**Total:** 2,912 linhas de código implementadas

---

## INTEGRAÇÃO COM ARQUITETURA EXISTENTE

### MinIO Client
Todos os serviços utilizam o MinIO client existente:
```python
from core.minio_client import get_minio_client
from core.config import get_settings

client = get_minio_client()
settings = get_settings()
```

### Airflow DAG
O DAG de cleanup roda automaticamente diariamente, integrado com:
- Airflow Scheduler
- Task monitoring
- XCom para compartilhar resultados entre tasks
- Logs centralizados

### FastAPI Endpoints
Endpoints integrados com:
- FastAPI router system
- Pydantic models para validation
- HTTPException para error handling
- OpenAPI documentation automática

---

## TESTES E VALIDAÇÃO

### Comandos de Teste

```bash
# Testar lifecycle policies (dry-run)
python3 << EOF
from storage.lifecycle import LifecyclePolicyManager, create_default_lifecycle_policies
from core.minio_client import get_minio_client
from core.config import get_settings

client = get_minio_client()
settings = get_settings()

# Criar e validar políticas
manager = LifecyclePolicyManager(client, settings.MINIO_BUCKET_NAME)
errors = manager.validate_policies()
print(f"Validation errors: {errors}")

# Aplicar políticas
success = manager.apply_lifecycle_policies()
print(f"Policies applied: {success}")

# Ver status
status = manager.get_policy_status()
print(f"Active policies: {status['policies_active']}")
EOF

# Testar quota management
python3 << EOF
from storage.quota import StorageQuotaManager
from core.minio_client import get_minio_client
from core.config import get_settings

client = get_minio_client()
settings = get_settings()

manager = StorageQuotaManager(client, settings.MINIO_BUCKET_NAME)

# Definir quota de teste
quota = manager.set_quota("user-test", "user", quota_gb=10.0)
print(f"Quota set: {quota.quota_gb}GB")

# Calcular uso atual
usage = manager.calculate_usage(prefix="jobs/")
print(f"Current usage: {usage.total_size / (1024**3):.2f}GB")
EOF

# Testar presigned URLs
python3 << EOF
from storage.presigned import PresignedURLGenerator
from core.minio_client import get_minio_client
from core.config import get_settings
from datetime import timedelta

client = get_minio_client()
settings = get_settings()

generator = PresignedURLGenerator(client, settings.MINIO_BUCKET_NAME)

# Gerar URL de teste (ajustar object_name conforme necessário)
url = generator.generate_download_url(
    "test-object.mp4",
    expires=timedelta(hours=1)
)
print(f"Generated URL: {url.url[:100]}...")
print(f"Expires at: {url.expires_at}")
EOF

# Testar duplicate detection (dry-run)
python3 << EOF
from storage.deduplication import DuplicateDetector
from core.minio_client import get_minio_client
from core.config import get_settings

client = get_minio_client()
settings = get_settings()

detector = DuplicateDetector(client, settings.MINIO_BUCKET_NAME)

# Scan para duplicatas
results = detector.scan_bucket(recursive=True)
print(f"Total files: {results['total_files']}")
print(f"Duplicates: {results['total_duplicates']}")
print(f"Wasted space: {results['wasted_space_gb']:.2f}GB")

# Relatório
report = detector.get_duplicate_report()
print(report)
EOF

# Testar cleanup service (dry-run)
python3 << EOF
from storage.cleanup import StorageCleanupService
from core.minio_client import get_minio_client
from core.config import get_settings

client = get_minio_client()
settings = get_settings()

service = StorageCleanupService(client, settings.MINIO_BUCKET_NAME)

# Cleanup dry-run
results = service.cleanup_all(dry_run=True)

total_files = sum(r.files_deleted for r in results)
total_space = sum(r.space_freed_mb for r in results)

print(f"Would delete: {total_files} files")
print(f"Would free: {total_space:.2f}MB")

for result in results:
    print(f"  {result.rule_name}: {result.files_deleted} files, {result.space_freed_mb:.2f}MB")
EOF
```

### Teste de API Endpoints

```bash
# Testar endpoint de outputs
curl -X GET "http://localhost:18000/downloads/job/test-job-123/outputs?expires_hours=2" \
  -H "accept: application/json" | jq

# Testar endpoint de vídeo
curl -X GET "http://localhost:18000/downloads/job/test-job-123/video/720p?download=true" \
  -H "accept: application/json" | jq

# Testar endpoint de HLS
curl -X GET "http://localhost:18000/downloads/job/test-job-123/hls/360p?expires_hours=3" \
  -H "accept: application/json" | jq
```

---

## MONITORAMENTO E LOGS

### Logs do Airflow DAG
```bash
# Ver logs do DAG de cleanup
docker exec transcode-airflow-scheduler airflow dags list | grep storage_cleanup

# Trigger manual para teste
docker exec transcode-airflow-scheduler \
  airflow dags trigger storage_cleanup_pipeline

# Ver execuções
docker exec transcode-airflow-scheduler \
  airflow dags list-runs -d storage_cleanup_pipeline
```

### Logs dos Serviços
Todos os serviços loggam para Python logging:
```python
import logging
logger = logging.getLogger(__name__)

# Logs incluem:
# - INFO: Operações normais
# - WARNING: Quotas próximas do limite, etc.
# - ERROR: Falhas em operações
# - DEBUG: Detalhes de hashing, URLs geradas, etc.
```

---

## PRÓXIMOS PASSOS (Futuro)

### Melhorias Potenciais

1. **Backup Manager** (não implementado na Sprint 4)
   - Backup automático para outro bucket/região
   - Restore de backups
   - Versionamento de arquivos

2. **Analytics Avançados**
   - Dashboard de uso de storage
   - Trends de crescimento
   - Top usuários por consumo

3. **Integração com Banco de Dados**
   - Salvar hashes de duplicatas no PostgreSQL
   - Histórico de quotas
   - Audit log de cleanups

4. **Webhooks de Notificação**
   - Notificar quando quota atinge 80%
   - Alertas de cleanup executado
   - Reports periódicos por email

---

## CONCLUSÃO

Sprint 4 implementa um sistema completo de gerenciamento de storage com:

- **Automação:** Lifecycle policies e DAG de cleanup diário
- **Segurança:** Presigned URLs com expiração configurável
- **Eficiência:** Detecção de duplicatas e limpeza automática
- **Controle:** Quotas por usuário com enforcement
- **APIs:** Endpoints REST para downloads seguros

Todos os componentes estão prontos para produção e integrados com a arquitetura existente do TranscodeFlow.

---

**Status Final:** ✅ SPRINT 4 COMPLETA - 100% IMPLEMENTADO
