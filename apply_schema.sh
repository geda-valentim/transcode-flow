#!/bin/bash
# Script para aplicar o schema do banco de dados

echo "🔧 Aplicando schema do banco de dados..."

# Aplicar schema como usuário postgres
PGPASSWORD=postgres psql -h localhost -U postgres -d transcode_db -f /home/transcode-flow/migrations/versions/001_initial_schema.sql

if [ $? -eq 0 ]; then
    echo "✅ Schema aplicado com sucesso!"

    # Listar tabelas criadas
    echo ""
    echo "📋 Tabelas criadas:"
    PGPASSWORD=postgres psql -h localhost -U postgres -d transcode_db -c "\dt"
else
    echo "❌ Erro ao aplicar schema"
    exit 1
fi
