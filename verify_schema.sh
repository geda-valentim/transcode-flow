#!/bin/bash
# Script para verificar se o schema do banco de dados está correto

echo "========================================="
echo "🔍 Verificando Schema do Banco de Dados"
echo "========================================="
echo ""

# Verificar banco local
echo "📊 Banco de Dados Local (localhost:5432)"
echo "----------------------------------------"
PGPASSWORD=postgres psql -h localhost -U postgres -d transcode_db -c "\d jobs" 2>/dev/null | grep -E "api_key" || echo "❌ Erro ao conectar no banco local"
echo ""

# Verificar banco Docker
echo "🐳 Banco de Dados Docker (container)"
echo "----------------------------------------"
docker exec transcode-postgres psql -U transcode_user -d transcode_db -c "\d jobs" 2>/dev/null | grep -E "api_key" || echo "⚠️  Container não está rodando. Execute 'docker compose up -d postgres' primeiro."
echo ""

echo "✅ Verificação concluída!"
echo ""
echo "O campo correto deve ser: 'api_key_id | integer'"
