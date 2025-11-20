#!/usr/bin/env python3
"""
Script para iniciar uma nova pipeline de transcodificação
Airflow 3 compatible - Uses API v2 with JWT token authentication
"""
import os

# Set environment variables BEFORE any other imports
os.environ.setdefault('TEMP_DIR', '/tmp/transcode-data')
os.environ.setdefault('DATABASE_URL', 'postgresql://transcode_user:CHANGE_ME_STRONG_PASSWORD_123@localhost:15432/transcode_db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:16379/0')
os.environ.setdefault('MINIO_HOST', 'localhost')
os.environ.setdefault('MINIO_PORT', '19000')
os.environ.setdefault('MINIO_ACCESS_KEY', 'admin')
os.environ.setdefault('MINIO_SECRET_KEY', 'CHANGE_ME_MINIO_PASSWORD_123')
os.environ.setdefault('SECRET_KEY', 'temp-secret-key')

import sys
import requests
from datetime import datetime, timezone
from pathlib import Path

# Configuração Airflow 3
AIRFLOW_URL = "http://localhost:18080"
AIRFLOW_USER = "admin"
AIRFLOW_PASSWORD = "CHANGE_ME_AIRFLOW_ADMIN_PASSWORD"
DAG_ID = "video_transcoding_pipeline"


def create_job_in_database(job_id: str, video_path: str):
    """
    Cria o job no banco de dados antes de iniciar a pipeline

    Args:
        job_id: ID do job
        video_path: Path do vídeo

    Returns:
        True se sucesso, False caso contrário
    """
    sys.path.insert(0, '/home/transcode-flow')

    try:
        from app.db import SessionLocal
        from app.models.job import Job, JobStatus

        db = SessionLocal()
        try:
            # Verificar se job já existe
            existing_job = db.query(Job).filter(Job.job_id == job_id).first()
            if existing_job:
                print(f"⚠️  Job {job_id} já existe no banco de dados")
                return True

            # Criar novo job
            job = Job(
                job_id=job_id,
                source_path=video_path,
                source_filename=Path(video_path).name,
                status=JobStatus.PENDING.value,  # Use .value to get the lowercase string
                created_at=datetime.now(timezone.utc)  # Airflow 3: Use timezone-aware datetime
            )
            db.add(job)
            db.commit()
            print(f"✅ Job criado no banco de dados: {job_id}")
            return True

        except Exception as e:
            print(f"❌ Erro ao criar job no banco: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return False


def get_airflow_token():
    """
    Get JWT authentication token from Airflow 3

    Returns:
        str: JWT access token
    """
    url = f"{AIRFLOW_URL}/auth/token"
    payload = {
        "username": AIRFLOW_USER,
        "password": AIRFLOW_PASSWORD
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code in [200, 201]:
            return response.json()["access_token"]
        else:
            raise Exception(f"Failed to get token: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Erro ao obter token de autenticação: {e}")
        return None


def trigger_via_airflow(video_path: str, job_id: str = None):
    """
    Trigger pipeline via Airflow 3 API v2 with JWT authentication

    Args:
        video_path: Path to the video file
        job_id: Optional job ID (auto-generated if not provided)
    """
    # Verificar se vídeo existe
    if not os.path.exists(video_path):
        print(f"❌ ERRO: Vídeo não encontrado: {video_path}")
        return False

    # Gerar job_id se não fornecido
    if not job_id:
        job_id = f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print("=" * 80)
    print("🎬 INICIANDO PIPELINE DE TRANSCODIFICAÇÃO - Airflow 3")
    print("=" * 80)
    print(f"📹 Vídeo: {video_path}")
    print(f"🆔 Job ID: {job_id}")
    print()

    # Nota: A DAG criará o job no banco de dados automaticamente
    # Remover criação antecipada do job para evitar problemas de permissão

    # Obter token JWT
    print("🔐 Obtendo token de autenticação...")
    token = get_airflow_token()
    if not token:
        return False
    print("✅ Token obtido com sucesso")
    print()

    # Endpoint da API v2 (Airflow 3)
    url = f"{AIRFLOW_URL}/api/v2/dags/{DAG_ID}/dagRuns"

    # Headers com token JWT
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Payload - Airflow 3 requires logical_date
    # Use current UTC time for immediate execution
    logical_date = datetime.now(timezone.utc).isoformat()

    payload = {
        "logical_date": logical_date,
        "conf": {
            "job_id": job_id,
            "video_path": video_path
        }
    }

    # Fazer requisição
    print("📡 Enviando requisição para Airflow API v2...")
    try:
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code in [200, 201]:
            try:
                data = response.json()
                dag_run_id = data.get("dag_run_id", data.get("id", "unknown"))

                print("✅ Pipeline iniciada com sucesso!")
                print()
                print("🔗 Detalhes:")
                print(f"   DAG Run ID: {dag_run_id}")
                print(f"   Job ID: {job_id}")
                print()
                print(f"📊 Acompanhe em: {AIRFLOW_URL}/dags/{DAG_ID}/grid")
                print()
                return True
            except Exception as e:
                print(f"✅ Pipeline iniciada! (Parsing error: {e})")
                print(f"📊 Acompanhe em: {AIRFLOW_URL}/dags/{DAG_ID}/grid")
                return True
        else:
            print(f"❌ Erro ao iniciar pipeline: {response.status_code}")
            print(f"Resposta: {response.text}")

            # Se for 404, dar instruções ao usuário
            if response.status_code == 404:
                print()
                print("💡 SOLUÇÃO ALTERNATIVA:")
                print(f"   1. Acesse: {AIRFLOW_URL}/dags/{DAG_ID}/grid")
                print("   2. Clique no botão 'Play' (▶) para disparar a DAG manualmente")
                print("   3. Use esta configuração:")
                print(f'      {{"job_id": "{job_id}", "video_path": "{video_path}"}}')

            return False

    except requests.exceptions.ConnectionError:
        print("❌ ERRO: Não foi possível conectar ao Airflow")
        print(f"   Verifique se o Airflow está rodando em {AIRFLOW_URL}")
        return False
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False


def copy_video_to_data_temp(source_video: str, job_id: str = None):
    """
    Copia o vídeo para /data/temp para processamento

    Args:
        source_video: Path do vídeo original
        job_id: ID do job

    Returns:
        Path do vídeo copiado
    """
    if not job_id:
        job_id = f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Criar diretório de destino
    dest_dir = Path(f"/data/temp/{job_id}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copiar vídeo
    source_path = Path(source_video)
    dest_path = dest_dir / source_path.name

    import shutil
    shutil.copy2(source_video, dest_path)

    return str(dest_path)


if __name__ == "__main__":
    # Parse argumentos
    if len(sys.argv) < 2:
        print("Uso: python3 trigger_pipeline.py <caminho_video> [job_id]")
        print()
        print("Exemplo:")
        print("  python3 trigger_pipeline.py /tmp/video.mp4")
        print("  python3 trigger_pipeline.py /tmp/video.mp4 my-custom-job-id")
        sys.exit(1)

    video_path = sys.argv[1]
    job_id = sys.argv[2] if len(sys.argv) > 2 else None

    # Trigger pipeline
    success = trigger_via_airflow(video_path, job_id)

    sys.exit(0 if success else 1)
