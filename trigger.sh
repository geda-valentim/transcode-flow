#!/bin/bash
#
# Script para disparar pipeline de transcodificação - Airflow 3
# Cria job diretamente no banco de dados
#

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Carregar variáveis de ambiente do .env
if [ -f .env ]; then
    set -a
    source <(grep -v '^#' .env | grep -v '^$' | sed 's/#.*//' | sed 's/[[:space:]]*$//')
    set +a
fi

# Configuração (usa variáveis de ambiente do .env ou valores padrão)
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_EXTERNAL_PORT:-15432}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASS="${POSTGRES_PASSWORD:-postgres}"
DB_NAME="${POSTGRES_DB:-transcode_db}"
AIRFLOW_URL="${AIRFLOW_URL:-http://localhost:18080}"

# Verificar argumentos
if [ $# -lt 1 ]; then
    echo "Uso: $0 <caminho_video> [opcoes]"
    echo ""
    echo "Exemplos:"
    echo "  $0 /data/temp/video.mp4"
    echo "  $0 /data/temp/video.mp4 --priority 8"
    echo ""
    echo "Opções:"
    echo "  --priority N    Prioridade do job (1-10, padrão: 5)"
    echo "  --no-hls        Desabilitar HLS"
    echo "  --no-audio      Desabilitar extração de áudio"
    echo "  --no-transcription  Desabilitar transcrição"
    exit 1
fi

# Parâmetros
VIDEO_PATH="$1"
PRIORITY=5
ENABLE_HLS=true
ENABLE_AUDIO=true
ENABLE_TRANSCRIPTION=true

# Parse opções
shift
while [[ $# -gt 0 ]]; do
    case $1 in
        --priority)
            PRIORITY="$2"
            shift 2
            ;;
        --no-hls)
            ENABLE_HLS=false
            shift
            ;;
        --no-audio)
            ENABLE_AUDIO=false
            shift
            ;;
        --no-transcription)
            ENABLE_TRANSCRIPTION=false
            shift
            ;;
        *)
            echo -e "${RED}❌ Opção desconhecida: $1${NC}"
            exit 1
            ;;
    esac
done

# Gerar job ID
JOB_ID="job-$(date +%Y%m%d-%H%M%S)"
FILENAME=$(basename "$VIDEO_PATH")

# Banner
echo ""
echo "================================================================================"
echo -e "${BLUE}🎬 DISPARANDO PIPELINE DE TRANSCODIFICAÇÃO - Airflow 3${NC}"
echo "================================================================================"
echo -e "${GREEN}📹 Vídeo:${NC} $VIDEO_PATH"
echo -e "${GREEN}🆔 Job ID:${NC} $JOB_ID"
echo -e "${GREEN}⚡ Prioridade:${NC} $PRIORITY"
echo -e "${GREEN}📺 HLS:${NC} $ENABLE_HLS"
echo -e "${GREEN}🎵 Áudio:${NC} $ENABLE_AUDIO"
echo -e "${GREEN}✍️  Transcrição:${NC} $ENABLE_TRANSCRIPTION"
echo ""

# Criar job no banco
echo -e "${YELLOW}💾 Criando job no banco de dados...${NC}"

PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME <<EOF
INSERT INTO jobs (
    job_id,
    status,
    priority,
    source_path,
    source_filename,
    enable_hls,
    enable_audio_extraction,
    enable_transcription,
    transcription_language,
    created_at
) VALUES (
    '$JOB_ID',
    'pending',
    $PRIORITY,
    '$VIDEO_PATH',
    '$FILENAME',
    $ENABLE_HLS,
    $ENABLE_AUDIO,
    $ENABLE_TRANSCRIPTION,
    'auto',
    NOW()
) RETURNING job_id, status, created_at;
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Job criado com sucesso!${NC}"
    echo ""
    echo "🔗 Detalhes:"
    echo "   Job ID: $JOB_ID"
    echo "   Status: pending"
    echo ""
    echo "📊 Acompanhe em:"
    echo "   Airflow UI: ${AIRFLOW_URL}/dags/video_transcoding_pipeline/grid"
    echo ""
    echo "💡 Para ver o status do job:"
    echo "   $0 --status $JOB_ID"
    echo ""
else
    echo ""
    echo -e "${RED}❌ Erro ao criar job no banco de dados${NC}"
    exit 1
fi
