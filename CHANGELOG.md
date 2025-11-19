# Changelog - Transcode Flow

## [Unreleased] - 2025-11-18

### Changed - Mapeamento de Portas

Todas as portas foram remapeadas para o range **1xxxx** para evitar conflitos com outros serviços.

#### Portas Atualizadas

| Serviço | Porta Antiga | Nova Porta | Mudança |
|---------|--------------|------------|---------|
| NGINX HTTP | 80 | **10080** | +10000 |
| NGINX HTTPS | 443 | **10443** | +10000 |
| Grafana | 3000 | **13000** | +10000 |
| PostgreSQL | 5432 | **15432** | +10000 |
| Flower | 5555 | **15555** | +10000 |
| Redis | 6379 | **16379** | +10000 |
| FastAPI | 8000 | **18000** | +10000 |
| Airflow | 8080 | **18080** | +10000 |
| MinIO API | 9000 | **19000** | +10000 |
| MinIO Console | 9001 | **19001** | +10000 |
| Prometheus | 9090 | **19090** | +10000 |
| Alertmanager | 9093 | **19093** | +10000 |
| Node Exporter | 9100 | **19100** | +10000 |
| Redis Exporter | 9121 | **19121** | +10000 |
| Postgres Exporter | 9187 | **19187** | +10000 |

#### Arquivos Modificados

- `docker-compose.yml` - Todas as portas atualizadas
- `README.md` - URLs atualizadas
- `QUICKSTART.md` - URLs atualizadas
- `Makefile` - Comandos health e docs atualizados
- `.env.example` - Adicionadas variáveis EXTERNAL_PORT e documentação de estratégia de portas
- **Novo:** `PORTS.md` - Documentação completa de portas

#### Migração

Se você já tinha o projeto rodando:

```bash
# Parar containers
docker compose down

# Atualizar .env (opcional - portas já estão no docker-compose.yml)
# nano .env

# Subir novamente
docker compose up -d

# Verificar saúde
make health
```

#### Novos Acessos

```bash
# Principais serviços
http://localhost:10080/docs    # API Documentation
http://localhost:18080          # Airflow
http://localhost:13000          # Grafana
http://localhost:19001          # MinIO Console
```

---

## [1.0.0] - 2025-11-18

### Added - Sprint 0: Infrastructure Setup

#### Estrutura do Projeto
- Criada estrutura completa de diretórios
- Configuração Docker Compose com 15 serviços
- Sistema de dados persistentes em `/data/`

#### Serviços Configurados
- PostgreSQL (banco de dados)
- Redis (broker Celery)
- MinIO (storage S3-compatible)
- Airflow (orchestration)
- Celery Worker (processamento)
- Flower (monitoring)
- FastAPI (API REST)
- NGINX (reverse proxy)
- Prometheus (métricas)
- Grafana (dashboards)
- Alertmanager (alertas)
- Exporters (Node, PostgreSQL, Redis)

#### Banco de Dados
- Schema completo com 4 tabelas
- 10+ índices otimizados
- Triggers e funções
- Suporte a JSONB para metadata

#### Documentação
- README.md completo
- QUICKSTART.md para setup rápido
- PORTS.md com mapeamento de portas
- 11 sprints documentados (Sprint 0-10)
- PRD completo

#### Automação
- Makefile com 20+ comandos
- Scripts de backup/restore
- Health checks configurados
- .gitignore configurado

#### Arquivos de Configuração
- `.env.example` com 150+ variáveis
- `docker-compose.yml` completo
- NGINX configurado
- Prometheus + Alertmanager
- Grafana preparado

---

**Formato baseado em [Keep a Changelog](https://keepachangelog.com/)**
