#!/usr/bin/env python3
"""
Script simples para disparar pipeline criando job direto no banco
Airflow 3 compatible - Monitora banco de dados para novos jobs
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import uuid

# Set environment variables
os.environ.setdefault('TEMP_DIR', '/tmp/transcode-data')
os.environ.setdefault('DATABASE_URL', 'postgresql://transcode_user:CHANGE_ME_STRONG_PASSWORD_123@localhost:15432/transcode_db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:16379/0')
os.environ.setdefault('MINIO_HOST', 'localhost')
os.environ.setdefault('MINIO_PORT', '19000')
os.environ.setdefault('SECRET_KEY', 'temp-secret-key')

# Add app to path
sys.path.insert(0, '/home/transcode-flow')

from app.db import SessionLocal
from app.models.job import Job


def create_job_direct(video_path: str):
    """
    Cria um job diretamente no banco de dados
    O Airflow monitorará e processará automaticamente

    Args:
        video_path: Caminho completo do vídeo
    """
    print("=" * 80)
    print("🎬 CRIANDO JOB NO BANCO - Airflow 3")
    print("=" * 80)
    print(f"📹 Vídeo: {video_path}")
    print()

    # Verificar se arquivo existe
    if not os.path.exists(video_path):
        print(f"❌ ERRO: Vídeo não encontrado: {video_path}")
        return False

    # Gerar job_id
    job_id = f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print(f"🆔 Job ID: {job_id}")
    print()

    try:
        # Conectar ao banco
        print("💾 Conectando ao banco de dados...")
        db = SessionLocal()

        try:
            # Criar job
            print("📝 Criando job...")

            job = Job(
                job_id=job_id,
                status="pending",  # lowercase para satisfazer constraint
                priority=5,
                source_path=video_path,
                source_filename=Path(video_path).name,
                enable_hls=True,
                enable_audio_extraction=True,
                enable_transcription=True,
                transcription_language="auto",
                created_at=datetime.now(timezone.utc),
            )

            db.add(job)
            db.commit()
            db.refresh(job)

            print("✅ Job criado com sucesso no banco de dados!")
            print()
            print("🔗 Detalhes:")
            print(f"   Job ID: {job.job_id}")
            print(f"   Status: {job.status}")
            print(f"   Criado em: {job.created_at}")
            print()
            print("📊 O Airflow processará automaticamente este job.")
            print("   Acompanhe em: http://localhost:18080/dags/video_transcoding_pipeline/grid")
            print()

            # Consultar job criado
            print("🔍 Verificando job criado...")
            job_check = db.query(Job).filter(Job.job_id == job_id).first()
            if job_check:
                print(f"   ✅ Job {job_id} confirmado no banco!")
            else:
                print(f"   ⚠️  Job não encontrado na verificação")

            return True

        except Exception as e:
            print(f"❌ Erro ao criar job no banco: {e}")
            db.rollback()
            import traceback
            traceback.print_exc()
            return False

        finally:
            db.close()

    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        import traceback
        traceback.print_exc()
        return False


def list_pending_jobs():
    """Lista jobs pendentes no banco"""
    try:
        db = SessionLocal()
        jobs = db.query(Job).filter(Job.status == "pending").all()

        print(f"\n📋 Jobs pendentes: {len(jobs)}")
        for job in jobs[:5]:
            print(f"   - {job.job_id}: {job.source_filename} ({job.created_at})")

        db.close()
        return True

    except Exception as e:
        print(f"Erro ao listar jobs: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 trigger_simple.py <caminho_video>")
        print()
        print("Exemplos:")
        print("  python3 trigger_simple.py /home/transcode-flow/data/temp/video.mp4")
        print("  python3 trigger_simple.py /data/temp/video.mp4")
        print()
        print("Nota: Use o caminho completo do vídeo")
        sys.exit(1)

    video_path = sys.argv[1]

    # Criar job
    success = create_job_direct(video_path)

    if success:
        # Listar jobs pendentes
        list_pending_jobs()

    sys.exit(0 if success else 1)
