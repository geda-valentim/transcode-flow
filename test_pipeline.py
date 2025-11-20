#!/usr/bin/env python3
"""
Script de teste completo da pipeline de transcodificação de vídeo
Executa todas as tarefas da pipeline sequencialmente sem o Airflow
"""
import sys
import os
from pathlib import Path

# Add paths to Python path
sys.path.insert(0, '/code/app')
sys.path.insert(0, '/home/transcode-flow/data/airflow/dags')

# Import all task functions
from transcode_pipeline.validation_tasks import (
    validate_video_task,
    generate_thumbnail_task
)
from transcode_pipeline.transcoding_tasks import (
    transcode_360p_task,
    transcode_720p_task,
    extract_audio_mp3_task,
    transcribe_audio_task
)
from transcode_pipeline.hls_tasks import prepare_hls_task
from transcode_pipeline.storage_tasks import (
    upload_to_minio_task,
    upload_outputs_task
)
from transcode_pipeline.database_tasks import (
    update_database_task,
    cleanup_temp_files_task
)
from transcode_pipeline.notification_tasks import send_notification_task


class MockTaskInstance:
    """Mock do TaskInstance do Airflow para simular XCom"""
    def __init__(self):
        self.xcom_data = {}

    def xcom_pull(self, task_ids, key='return_value'):
        """Simula o xcom_pull do Airflow"""
        if isinstance(task_ids, list):
            return [self.xcom_data.get(tid, {}).get(key) for tid in task_ids]
        return self.xcom_data.get(task_ids, {}).get(key)

    def xcom_push(self, key, value, task_id=None):
        """Simula o xcom_push do Airflow"""
        if task_id not in self.xcom_data:
            self.xcom_data[task_id] = {}
        self.xcom_data[task_id][key] = value


class MockDagRun:
    """Mock do DagRun do Airflow"""
    def __init__(self, job_id, video_id, video_path):
        self.conf = {
            'job_id': job_id,
            'video_id': video_id,
            'video_path': video_path
        }


class MockContext:
    """Mock do contexto do Airflow"""
    def __init__(self, ti, video_id, video_path, job_id):
        self.ti = ti
        self.dag_run = MockDagRun(job_id, video_id, video_path)
        self.params = {
            'video_id': video_id,
            'video_path': video_path,
            'job_id': job_id
        }
        # Configuração para tasks HLS
        self.resolution = None
        self.input_path_key = None
        self.output_key = None


def run_pipeline(video_path: str, video_id: str = "test-video-001"):
    """
    Executa a pipeline completa de transcodificação

    Args:
        video_path: Caminho para o vídeo de entrada
        video_id: ID único para o vídeo (usado no banco e storage)
    """
    print("=" * 80)
    print("🎬 INICIANDO TESTE DA PIPELINE DE TRANSCODIFICAÇÃO")
    print("=" * 80)
    print(f"📹 Vídeo: {video_path}")
    print(f"🆔 Video ID: {video_id}")
    print()

    # Verificar se o arquivo existe
    if not os.path.exists(video_path):
        print(f"❌ ERRO: Arquivo não encontrado: {video_path}")
        return False

    # Criar mock do TaskInstance e Context
    ti = MockTaskInstance()
    job_id = f"job-{video_id}"
    context = MockContext(ti, video_id, video_path, job_id)

    # Criar job no banco de dados
    print("\n" + "─" * 80)
    print("💾 PREPARAÇÃO: CRIANDO JOB NO BANCO DE DADOS")
    print("─" * 80)

    from app.db import SessionLocal
    from app.models.job import Job, JobStatus
    from datetime import datetime

    db = SessionLocal()
    try:
        # Verificar se job já existe
        existing_job = db.query(Job).filter(Job.job_id == job_id).first()
        if existing_job:
            print(f"⚠️  Job {job_id} já existe, será reutilizado")
            job = existing_job
        else:
            # Criar novo job
            job = Job(
                job_id=job_id,
                video_id=video_id,
                user_id="test-user",
                source_path=video_path,
                status=JobStatus.PENDING,
                created_at=datetime.utcnow()
            )
            db.add(job)
            db.commit()
            print(f"✅ Job criado: {job_id}")
    except Exception as e:
        print(f"❌ Erro ao criar job: {e}")
        db.rollback()
        return False
    finally:
        db.close()

    try:
        # ============================================================================
        # FASE 1: VALIDAÇÃO
        # ============================================================================
        print("\n" + "─" * 80)
        print("📋 FASE 1: VALIDAÇÃO DO VÍDEO")
        print("─" * 80)

        # Criar dicionário de contexto compatível com Airflow
        airflow_context = {
            'dag_run': context.dag_run,
            'ti': context.ti,
            **context.params
        }
        result = validate_video_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='validate_video')
        print("✅ Validação concluída")
        print(f"   Duração: {result.get('duration', 'N/A')}s")
        print(f"   Resolução: {result.get('width', 'N/A')}x{result.get('height', 'N/A')}")
        print(f"   Codec: {result.get('codec', 'N/A')}")

        # ============================================================================
        # FASE 2: UPLOAD DO VÍDEO ORIGINAL
        # ============================================================================
        print("\n" + "─" * 80)
        print("☁️  FASE 2: UPLOAD DO VÍDEO ORIGINAL PARA MINIO")
        print("─" * 80)

        result = upload_to_minio_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='upload_to_minio')
        print("✅ Upload concluído")
        print(f"   URL: {result.get('minio_url', 'N/A')}")

        # ============================================================================
        # FASE 3: GERAÇÃO DE THUMBNAIL
        # ============================================================================
        print("\n" + "─" * 80)
        print("🖼️  FASE 3: GERAÇÃO DE THUMBNAIL")
        print("─" * 80)

        result = generate_thumbnail_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='generate_thumbnail')
        print("✅ Thumbnail gerado")
        print(f"   Arquivo: {result.get('thumbnail_path', 'N/A')}")

        # ============================================================================
        # FASE 4: TRANSCODIFICAÇÕES PARALELAS
        # ============================================================================
        print("\n" + "─" * 80)
        print("🎥 FASE 4: TRANSCODIFICAÇÃO (360p, 720p, Audio, Transcription)")
        print("─" * 80)

        # 4a. Transcode 360p
        print("\n  → Transcodificando para 360p...")
        result = transcode_360p_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='transcode_360p')
        print(f"  ✅ 360p: {result.get('output_path', 'N/A')}")

        # 4b. Transcode 720p
        print("\n  → Transcodificando para 720p...")
        result = transcode_720p_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='transcode_720p')
        print(f"  ✅ 720p: {result.get('output_path', 'N/A')}")

        # 4c. Extract Audio MP3
        print("\n  → Extraindo áudio MP3...")
        result = extract_audio_mp3_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='extract_audio_mp3')
        print(f"  ✅ Audio MP3: {result.get('output_path', 'N/A')}")

        # 4d. Transcribe Audio
        print("\n  → Transcrevendo áudio com Whisper...")
        result = transcribe_audio_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='transcribe_audio')
        print(f"  ✅ Transcrição: {result.get('transcript_path', 'N/A')}")

        # ============================================================================
        # FASE 5: PREPARAÇÃO HLS
        # ============================================================================
        print("\n" + "─" * 80)
        print("📦 FASE 5: PREPARAÇÃO HLS (360p, 720p)")
        print("─" * 80)

        # 5a. Prepare HLS 360p
        print("\n  → Preparando HLS 360p...")
        context.resolution = '360p'
        context.input_path_key = '360p_path'
        context.output_key = 'hls_360p_dir'
        hls_context = {**airflow_context, 'params': {
            'resolution': '360p',
            'input_path_key': '360p_path',
            'output_key': 'hls_360p_dir'
        }}
        result = prepare_hls_task(**hls_context)
        ti.xcom_push('return_value', result, task_id='prepare_hls_360p')
        print(f"  ✅ HLS 360p: {result.get('hls_360p_dir', 'N/A')}")

        # 5b. Prepare HLS 720p
        print("\n  → Preparando HLS 720p...")
        context.resolution = '720p'
        context.input_path_key = '720p_path'
        context.output_key = 'hls_720p_dir'
        hls_context = {**airflow_context, 'params': {
            'resolution': '720p',
            'input_path_key': '720p_path',
            'output_key': 'hls_720p_dir'
        }}
        result = prepare_hls_task(**hls_context)
        ti.xcom_push('return_value', result, task_id='prepare_hls_720p')
        print(f"  ✅ HLS 720p: {result.get('hls_720p_dir', 'N/A')}")

        # ============================================================================
        # FASE 6: UPLOAD DE OUTPUTS
        # ============================================================================
        print("\n" + "─" * 80)
        print("☁️  FASE 6: UPLOAD DE TODOS OS OUTPUTS PARA MINIO")
        print("─" * 80)

        result = upload_outputs_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='upload_outputs')
        print("✅ Uploads concluídos")
        print(f"   Arquivos enviados: {len(result.get('uploaded_files', []))}")
        for file_info in result.get('uploaded_files', []):
            print(f"   - {file_info.get('type', 'N/A')}: {file_info.get('url', 'N/A')}")

        # ============================================================================
        # FASE 7: ATUALIZAÇÃO DO BANCO DE DADOS
        # ============================================================================
        print("\n" + "─" * 80)
        print("💾 FASE 7: ATUALIZAÇÃO DO BANCO DE DADOS")
        print("─" * 80)

        result = update_database_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='update_database')
        print("✅ Banco de dados atualizado")
        print(f"   Status: {result.get('status', 'N/A')}")

        # ============================================================================
        # FASE 8: LIMPEZA DE ARQUIVOS TEMPORÁRIOS
        # ============================================================================
        print("\n" + "─" * 80)
        print("🧹 FASE 8: LIMPEZA DE ARQUIVOS TEMPORÁRIOS")
        print("─" * 80)

        result = cleanup_temp_files_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='cleanup_temp_files')
        print("✅ Limpeza concluída")
        print(f"   Arquivos removidos: {result.get('files_removed', 0)}")
        print(f"   Espaço liberado: {result.get('space_freed', 0)} bytes")

        # ============================================================================
        # FASE 9: NOTIFICAÇÃO
        # ============================================================================
        print("\n" + "─" * 80)
        print("📢 FASE 9: ENVIO DE NOTIFICAÇÃO")
        print("─" * 80)

        result = send_notification_task(**airflow_context)
        ti.xcom_push('return_value', result, task_id='send_notification')
        print("✅ Notificação enviada")
        print(f"   Status: {result.get('status', 'N/A')}")

        # ============================================================================
        # CONCLUSÃO
        # ============================================================================
        print("\n" + "=" * 80)
        print("✨ PIPELINE CONCLUÍDA COM SUCESSO!")
        print("=" * 80)
        print()

        return True

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ ERRO NA PIPELINE: {str(e)}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Configuração do vídeo de teste
    VIDEO_PATH = "/tmp/video.mp4"
    VIDEO_ID = "test-video-" + os.path.basename(VIDEO_PATH).replace('.', '-')

    # Executar pipeline
    success = run_pipeline(VIDEO_PATH, VIDEO_ID)

    # Exit code
    sys.exit(0 if success else 1)
