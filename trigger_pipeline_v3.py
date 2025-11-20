#!/usr/bin/env python3
"""
Script para disparar pipeline de transcodificação via FastAPI
Airflow 3 compatible - Uses FastAPI endpoint instead of Airflow API
"""
import requests
import sys
from pathlib import Path

# Configuração
FASTAPI_URL = "http://localhost:18000"
API_KEY = "test-api-key-123"  # Você precisará criar uma API key primeiro
DAG_ID = "video_transcoding_pipeline"


def create_job_filesystem(video_path: str):
    """
    Cria um job usando o endpoint /api/v1/jobs/filesystem da FastAPI

    Args:
        video_path: Caminho completo do vídeo no filesystem
    """
    print("=" * 80)
    print("🎬 DISPARANDO PIPELINE VIA FASTAPI - Airflow 3")
    print("=" * 80)
    print(f"📹 Vídeo: {video_path}")
    print()

    # Endpoint da FastAPI
    url = f"{FASTAPI_URL}/api/v1/jobs/filesystem"

    # Headers com API key
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

    # Payload
    payload = {
        "source_path": video_path,
        "target_resolutions": ["360p", "720p"],
        "enable_hls": True,
        "enable_audio_extraction": True,
        "enable_transcription": True,
        "transcription_language": "auto",
        "priority": 5,
        "metadata": {
            "source": "CLI trigger script",
            "triggered_at": "manual"
        }
    }

    print("📡 Enviando requisição para FastAPI...")
    print(f"   Endpoint: {url}")
    print()

    try:
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 201:
            data = response.json()
            job_id = data.get("job_id")

            print("✅ Job criado com sucesso!")
            print()
            print("🔗 Detalhes:")
            print(f"   Job ID: {job_id}")
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message')}")
            print()
            print(f"📊 Acompanhe em:")
            print(f"   FastAPI: {FASTAPI_URL}/api/v1/jobs/{job_id}")
            print(f"   Airflow: http://localhost:18080/dags/{DAG_ID}/grid")
            print()
            return True

        elif response.status_code == 401:
            print("❌ Erro de autenticação!")
            print()
            print("🔑 Você precisa criar uma API key primeiro:")
            print("   1. Acesse a FastAPI docs: http://localhost:18000/docs")
            print("   2. Crie uma API key via POST /api/v1/api-keys/")
            print("   3. Atualize a variável API_KEY neste script")
            print()
            return False

        else:
            print(f"❌ Erro ao criar job: {response.status_code}")
            print(f"Resposta: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ ERRO: Não foi possível conectar à FastAPI")
        print(f"   Verifique se a FastAPI está rodando em {FASTAPI_URL}")
        print()
        print("💡 Para iniciar a FastAPI:")
        print("   docker compose ps fastapi")
        print("   docker compose logs fastapi")
        return False

    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_job_status(job_id: str):
    """
    Consulta o status de um job

    Args:
        job_id: ID do job
    """
    url = f"{FASTAPI_URL}/api/v1/jobs/{job_id}"
    headers = {"X-API-Key": API_KEY}

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            print(f"Status do Job {job_id}:")
            print(f"  Status: {data.get('status')}")
            print(f"  Progress: {data.get('progress', 'N/A')}")
            return True
        else:
            print(f"Erro ao consultar job: {response.status_code}")
            return False

    except Exception as e:
        print(f"Erro: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 trigger_pipeline_v3.py <caminho_video>")
        print()
        print("Exemplos:")
        print("  python3 trigger_pipeline_v3.py /home/transcode-flow/data/temp/video.mp4")
        print("  python3 trigger_pipeline_v3.py /data/temp/video.mp4")
        print()
        print("Nota: O caminho deve ser acessível pelo container FastAPI")
        sys.exit(1)

    video_path = sys.argv[1]

    # Verificar se o arquivo existe (localmente)
    if not Path(video_path).exists():
        print(f"⚠️  Aviso: Arquivo não encontrado localmente: {video_path}")
        print("   Tentando mesmo assim (pode estar no container)...")
        print()

    # Criar job
    success = create_job_filesystem(video_path)
    sys.exit(0 if success else 1)
