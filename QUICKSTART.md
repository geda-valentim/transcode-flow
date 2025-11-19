# 🚀 Transcode Flow - Quick Start

## 📋 Pré-requisitos

- Docker 20.10+
- Docker Compose 2.0+
- 100GB+ espaço em disco
- 8GB+ RAM

## ⚡ Setup Rápido (5 minutos)

### 1. Configure o ambiente

```bash
# Copie o arquivo de configuração
cp .env.example .env

# Edite as senhas (IMPORTANTE!)
nano .env
```

**⚠️ ALTERE ESTAS SENHAS:**
- POSTGRES_PASSWORD
- MINIO_ROOT_PASSWORD
- AIRFLOW__CORE__FERNET_KEY
- SECRET_KEY
- GRAFANA_ADMIN_PASSWORD

**💡 Dica:** Use `make init` para setup automático!

### 2. Inicie o projeto

```bash
# Opção 1: Setup automático (recomendado)
make init

# Opção 2: Manual
docker compose up -d
make migrate
```

### 3. Verifique a saúde

```bash
make health
```

## 🌐 Acesse os Serviços

| Serviço | URL | Login |
|---------|-----|-------|
| **API Docs** | http://localhost:10080/docs | - |
| **Airflow** | http://localhost:18080 | admin / (senha do .env) |
| **Grafana** | http://localhost:13000 | admin / (senha do .env) |
| **MinIO Console** | http://localhost:19001 | admin / (senha do .env) |
| **Flower** | http://localhost:15555 | admin / (senha do .env) |
| **Prometheus** | http://localhost:19090 | - |

## 📝 Comandos Úteis

```bash
# Ver logs
make logs

# Ver logs da API
make logs-api

# Parar tudo
make down

# Reiniciar
make restart

# Backup do banco
make backup

# Testes
make test

# Acessar shell da API
make shell-api

# Acessar PostgreSQL
make shell-pg

# Ver todos os comandos
make help
```

## ✅ Verificação

### 1. Teste a API

```bash
curl http://localhost:10080/health
```

**Resposta esperada:**
```json
{
  "status": "healthy",
  "service": "transcode-flow-api",
  "version": "1.0.0"
}
```

### 2. Verifique os containers

```bash
docker compose ps
```

**Todos devem estar "Up" (healthy)**

### 3. Teste o banco de dados

```bash
docker compose exec postgres psql -U transcode_user -d transcode_db -c "SELECT COUNT(*) FROM api_keys;"
```

**Deve retornar 1** (API key padrão)

## 🐛 Problemas Comuns

### "Port already in use"

```bash
# Verifique o que está usando a porta
sudo lsof -i :80

# Pare o serviço ou mude a porta no docker-compose.yml
```

### "Cannot connect to Docker daemon"

```bash
# Inicie o Docker
sudo systemctl start docker

# Ou no WSL2
sudo service docker start
```

### "Out of disk space"

```bash
# Limpe containers antigos
docker system prune -a

# Verifique espaço
df -h
```

## 📚 Próximos Passos

1. ✅ **Leia a documentação:** [docs/README.md](docs/README.md)
2. ✅ **Siga os sprints:** [docs/sprints/](docs/sprints/)
3. ✅ **Sprint 1:** Implemente a API de upload
4. ✅ **Sprint 2:** Configure o Airflow DAG
5. ✅ **Sprint 3:** Integre FFmpeg e Whisper

## 🔒 Segurança

**ANTES DE IR PARA PRODUÇÃO:**

1. ✅ Altere TODAS as senhas padrão
2. ✅ Configure SSL/TLS (Sprint 10)
3. ✅ Configure firewall
4. ✅ Habilite backups automáticos
5. ✅ Revise as permissões de API keys

## 📞 Precisa de Ajuda?

- 📖 [README.md](README.md) - Documentação completa
- 📋 [PRD.md](docs/PRD.md) - Requirements
- 🏃 [Sprints](docs/sprints/) - Planejamento
- 🐛 [Issues](https://github.com/your-repo/issues)

---

**Happy Coding! 🎉**
