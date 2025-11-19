# Transcode Flow

**Video Transcoding Service Platform** com transcodificação multi-resolução, streaming HLS, extração de áudio e transcrição automática.

---

## 🚀 Quick Start

### Pré-requisitos

- Docker 20.10+ e Docker Compose 2.0+
- 100GB+ de espaço livre em disco
- 8GB+ RAM
- CPU com 4+ cores

### 1. Clone o Repositório

```bash
git clone <repository-url> /home/transcode-flow
cd /home/transcode-flow
```

### 2. Configure Variáveis de Ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite e atualize as senhas (IMPORTANTE!)
nano .env
```

**Senhas que DEVEM ser alteradas:**
- `POSTGRES_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `AIRFLOW__CORE__FERNET_KEY`
- `AIRFLOW__WEBSERVER__SECRET_KEY`
- `SECRET_KEY`
- `GRAFANA_ADMIN_PASSWORD`

### 3. Iniciar os Serviços

```bash
# Subir todos os containers
docker compose up -d

# Verificar status
docker compose ps

# Ver logs
docker compose logs -f
```

### 4. Inicializar o Banco de Dados

```bash
# Executar migração do schema
docker compose exec postgres psql -U transcode_user -d transcode_db -f /migrations/versions/001_initial_schema.sql
```

### 5. Verificar Saúde dos Serviços

```bash
# API
curl http://localhost/health

# Prometheus
curl http://localhost:9090/-/healthy

# Grafana
curl http://localhost:3000/api/health

# MinIO
curl http://localhost:9000/minio/health/live
```

---

## 📋 Serviços Disponíveis

| Serviço | URL | Descrição |
|---------|-----|-----------|
| **API** | http://localhost:10080/api | FastAPI REST API |
| **Docs** | http://localhost:10080/docs | Documentação interativa (Swagger) |
| **Airflow** | http://localhost:18080 | Orquestração de workflows |
| **Flower** | http://localhost:15555 | Monitoramento Celery |
| **MinIO Console** | http://localhost:19001 | Storage console |
| **Grafana** | http://localhost:13000 | Dashboards de métricas |
| **Prometheus** | http://localhost:19090 | Metrics collection |

### Credenciais Padrão

**Airflow:**
- User: `admin`
- Password: (definido em `.env`)

**Grafana:**
- User: `admin`
- Password: (definido em `.env`)

**MinIO:**
- User: `admin`
- Password: (definido em `.env`)

---

## 🏗️ Estrutura do Projeto

```
/home/transcode-flow/
├── app/                    # Aplicação FastAPI
│   ├── api/               # Endpoints da API
│   ├── models/            # Modelos SQLAlchemy
│   ├── tasks/             # Tarefas Celery
│   ├── utils/             # Utilitários
│   ├── main.py            # Aplicação principal
│   ├── requirements.txt   # Dependências Python
│   └── Dockerfile         # Docker image
├── data/                   # Dados persistentes (GITIGNORED)
│   ├── airflow/           # DAGs, logs, plugins
│   ├── postgres/          # Banco de dados
│   ├── minio/             # Armazenamento de vídeos
│   ├── redis/             # Cache Redis
│   ├── prometheus/        # Métricas
│   ├── grafana/           # Dashboards
│   ├── backups/           # Backups
│   ├── logs/              # Logs da aplicação
│   └── temp/              # Arquivos temporários
├── migrations/             # Migrações do banco
├── nginx/                  # Configuração NGINX
├── prometheus/             # Configuração Prometheus
├── tests/                  # Testes automatizados
├── docs/                   # Documentação
│   ├── PRD.md             # Product Requirements
│   └── sprints/           # Sprint planning
├── docker-compose.yml      # Orquestração de containers
├── .env.example            # Variáveis de ambiente (template)
└── README.md               # Este arquivo
```

---

## 🎯 Funcionalidades

### Transcodificação de Vídeo
- ✅ Múltiplas resoluções (360p, 720p)
- ✅ Detecção automática de resolução
- ✅ Otimização com FFmpeg
- ✅ Cálculo de taxa de compressão

### Streaming HLS
- ✅ Segmentação de vídeo (10s)
- ✅ Playlists M3U8
- ✅ CORS configurado
- ✅ Suporte a múltiplas resoluções

### Extração de Áudio
- ✅ Formato MP3 (192kbps)
- ✅ Qualidade otimizada

### Transcrição Automática
- ✅ OpenAI Whisper integration
- ✅ Suporte a 90+ idiomas
- ✅ Detecção automática de idioma
- ✅ Múltiplos formatos (TXT, SRT, VTT, JSON)
- ✅ Seleção automática de modelo

### Gerenciamento
- ✅ API Keys com permissões
- ✅ Rate limiting
- ✅ Quotas de armazenamento
- ✅ Webhooks para notificações
- ✅ Rastreamento de progresso em tempo real

### Monitoramento
- ✅ Métricas Prometheus
- ✅ Dashboards Grafana
- ✅ Alertas configuráveis
- ✅ Health checks

---

## 🔧 Desenvolvimento

### Executar Testes

```bash
# Testes unitários
docker compose exec fastapi pytest

# Com coverage
docker compose exec fastapi pytest --cov=app --cov-report=html

# Ver relatório
open htmlcov/index.html
```

### Logs

```bash
# Todos os serviços
docker compose logs -f

# Serviço específico
docker compose logs -f fastapi
docker compose logs -f postgres
docker compose logs -f celery-worker
```

### Reconstruir Containers

```bash
# Parar tudo
docker compose down

# Reconstruir
docker compose build

# Subir novamente
docker compose up -d
```

### Acessar Container

```bash
# FastAPI
docker compose exec fastapi bash

# PostgreSQL
docker compose exec postgres psql -U transcode_user -d transcode_db

# Redis
docker compose exec redis redis-cli
```

---

## 📊 Monitoramento

### Prometheus Metrics

Acesse: http://localhost:9090

**Queries úteis:**
```promql
# Taxa de requisições da API
rate(api_requests_total[5m])

# Jobs em fila
jobs_queued

# Uso de CPU
100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

### Grafana Dashboards

Acesse: http://localhost:3000

**Dashboards disponíveis:**
1. System Overview
2. Job Processing
3. Video Processing Metrics
4. API Performance

---

## 🔐 Segurança

### Boas Práticas

1. **Altere todas as senhas padrão** no arquivo `.env`
2. **Não commite** o arquivo `.env` no git
3. **Use SSL/TLS** em produção
4. **Configure firewall** para limitar acesso
5. **Mantenha backups** regulares

### Gerando Senhas Fortes

```bash
# Fernet Key para Airflow
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Secret Key genérica
openssl rand -hex 32
```

---

## 🗄️ Backup e Restore

### Backup do Banco de Dados

```bash
# Backup manual
docker compose exec postgres pg_dump -U transcode_user transcode_db | gzip > backup_$(date +%Y%m%d).sql.gz

# Backup automático (configurado no docker-compose)
```

### Restore do Banco de Dados

```bash
# Descompactar e restaurar
gunzip -c backup_20251118.sql.gz | docker compose exec -T postgres psql -U transcode_user -d transcode_db
```

### Backup do MinIO

```bash
# Copiar todos os dados
cp -r ./data/minio ./backups/minio_$(date +%Y%m%d)
```

---

## 🐛 Troubleshooting

### Problema: Serviços não sobem

```bash
# Verificar logs
docker compose logs

# Verificar recursos
docker stats

# Limpar e recomeçar
docker compose down -v
docker compose up -d
```

### Problema: Porta já em uso

```bash
# Verificar portas em uso
sudo lsof -i :80
sudo lsof -i :8080
sudo lsof -i :5432

# Parar serviço conflitante ou alterar porta no docker-compose.yml
```

### Problema: Banco de dados não conecta

```bash
# Verificar se PostgreSQL está rodando
docker compose ps postgres

# Ver logs do PostgreSQL
docker compose logs postgres

# Testar conexão
docker compose exec postgres pg_isready -U transcode_user
```

---

## 📚 Documentação

- [PRD Completo](./docs/PRD.md)
- [Sprint Planning](./docs/sprints/)
- [API Documentation](http://localhost/docs) (quando rodando)

---

## 🤝 Contribuindo

1. Crie uma branch: `git checkout -b feature/nova-feature`
2. Commit suas mudanças: `git commit -m 'Add nova feature'`
3. Push para a branch: `git push origin feature/nova-feature`
4. Abra um Pull Request

---

## 📄 Licença

Projeto interno - Todos os direitos reservados

---

## 🆘 Suporte

Para suporte:
1. Consulte a [documentação](./docs/)
2. Verifique os [issues conhecidos](https://github.com/your-repo/issues)
3. Entre em contato com o time de desenvolvimento

---

**Última Atualização:** 2025-11-18
**Versão:** 1.0.0
**Status:** Sprint 0 - Infrastructure Setup
