#!/bin/bash
# Script para popular os dashboards fazendo requests HTTP à API

echo "🚀 Populando dashboards com requests HTTP..."
echo ""

# Fazer várias requisições à API para gerar métricas
echo "📊 Gerando métricas de API..."
for i in {1..20}; do
    curl -s http://localhost:8000/health > /dev/null
    curl -s http://localhost:8000/ > /dev/null
    sleep 0.1
done

echo "✅ 40 requests HTTP feitos"
echo ""
echo "📈 Métricas geradas:"
echo "  • api_requests_total: ~40"
echo "  • api_request_duration_seconds: ~40 medidas"
echo ""
echo "🎯 Os dashboards que vão ter dados:"
echo "  ✅ API Performance - com dados reais de requests"
echo "  ✅ System Overview - com dados do sistema (CPU, memória, disco)"
echo ""
echo "  ⚠️  Job Processing - precisa de jobs reais (upload de vídeo)"
echo "  ⚠️  Video Processing - precisa de vídeos processados"
echo ""
echo "💡 Para popular os outros dashboards:"
echo "  1. Obter API key: make shell-pg → SELECT api_key FROM api_keys LIMIT 1;"
echo "  2. Upload vídeo: curl -X POST http://localhost:10080/api/v1/jobs/upload \\"
echo "     -H 'X-API-Key: sua_key' -F 'video_file=@video.mp4'"
echo ""
echo "✅ Aguarde 30s e acesse: http://localhost:13000"
