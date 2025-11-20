#!/bin/bash
# Script para iniciar um novo job de transcodificação via API do Airflow

VIDEO_PATH="${1:-/tmp/video.mp4}"
JOB_ID="job-$(date +%Y%m%d-%H%M%S)"

echo "=================================="
echo "🎬 Iniciando Pipeline de Transcodificação"
echo "=================================="
echo "📹 Vídeo: $VIDEO_PATH"
echo "🆔 Job ID: $JOB_ID"
echo ""

# Verificar se o vídeo existe
if [ ! -f "$VIDEO_PATH" ]; then
    echo "❌ ERRO: Vídeo não encontrado: $VIDEO_PATH"
    exit 1
fi

echo "📡 Enviando requisição para Airflow..."

# Trigger DAG via API
RESPONSE=$(curl -s -X POST "http://localhost:18080/api/v1/dags/video_transcoding_pipeline/dagRuns" \
  -H "Content-Type: application/json" \
  -u "admin:CHANGE_ME_AIRFLOW_ADMIN_PASSWORD" \
  -d "{
    \"conf\": {
      \"job_id\": \"$JOB_ID\",
      \"video_path\": \"$VIDEO_PATH\"
    }
  }")

# Verificar resposta
if echo "$RESPONSE" | grep -q "dag_run_id"; then
    DAG_RUN_ID=$(echo "$RESPONSE" | grep -o '"dag_run_id":"[^"]*' | cut -d'"' -f4)
    echo "✅ Pipeline iniciada com sucesso!"
    echo ""
    echo "🔗 Detalhes:"
    echo "   DAG Run ID: $DAG_RUN_ID"
    echo "   Job ID: $JOB_ID"
    echo ""
    echo "📊 Acompanhe em: http://localhost:18080/dags/video_transcoding_pipeline/grid"
    echo ""
    echo "🔍 Ver logs:"
    echo "   docker exec -it airflow-webserver airflow tasks logs video_transcoding_pipeline $DAG_RUN_ID"
else
    echo "❌ Erro ao iniciar pipeline"
    echo "Resposta: $RESPONSE"
    exit 1
fi
