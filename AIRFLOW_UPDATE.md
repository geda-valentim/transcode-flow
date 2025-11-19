# Atualização do Airflow - Correção de Problemas

## 🔧 Problema Identificado

O Airflow estava em constante reinício devido a incompatibilidades com a versão latest.

### Erro Principal:
```
airflow command error: argument GROUP_OR_COMMAND: Command `airflow webserver` has been removed.
Please use `airflow api-server`, see help above.
```

## ✅ Solução Implementada

### 1. Pin da Versão do Airflow
- **Antes**: `apache/airflow:latest` (versão instável)
- **Depois**: `apache/airflow:2.10.4` (versão estável LTS)

### 2. Novo Serviço: airflow-init
Adicionado container de inicialização para:
- Executar migrações do banco de dados
- Criar usuário admin automaticamente
- Garantir dependências antes de iniciar webserver/scheduler

### 3. Atualizações nas Variáveis de Ambiente

**Mudanças no `.env.example`:**
```bash
# Novos
AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=CHANGE_ME_AIRFLOW_ADMIN_PASSWORD

# Atualizado
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN  # Era AIRFLOW__CORE__SQL_ALCHEMY_CONN
AIRFLOW__API__AUTH_BACKENDS          # Era AIRFLOW__API__AUTH_BACKEND
```

### 4. Melhorias nos Health Checks
Adicionado `start_period: 30s` para dar tempo aos serviços iniciarem corretamente.

### 5. Remoção do version: '3.8'
Removido aviso de deprecação do docker-compose.

## 📋 Containers Atualizados

| Serviço | Imagem Anterior | Nova Imagem |
|---------|----------------|-------------|
| airflow-webserver | apache/airflow:latest | apache/airflow:2.10.4 |
| airflow-scheduler | apache/airflow:latest | apache/airflow:2.10.4 |
| celery-worker | apache/airflow:latest | apache/airflow:2.10.4 |
| airflow-init | - | apache/airflow:2.10.4 (novo) |

## 🔄 Ordem de Inicialização

1. **postgres** + **redis** (infraestrutura)
2. **airflow-init** (setup do banco)
3. **airflow-webserver** + **airflow-scheduler** + **celery-worker**

## 🎯 Acesso ao Airflow

**URL**: http://localhost:18080

**Credenciais (padrão do .env)**:
- Username: `admin`
- Password: (definido em `AIRFLOW_ADMIN_PASSWORD`)

## 📝 Comandos Úteis

```bash
# Ver logs do init
docker compose logs airflow-init

# Ver logs do webserver
docker compose logs -f airflow-webserver

# Ver logs do scheduler
docker compose logs -f airflow-scheduler

# Reiniciar apenas Airflow
docker compose restart airflow-webserver airflow-scheduler celery-worker

# Recriar banco do Airflow (cuidado!)
docker compose run --rm airflow-init
```

## ⚠️ Problemas Conhecidos

### Download Grande
A imagem `apache/airflow:2.10.4` tem aproximadamente **890MB**.
Primeira inicialização pode levar 5-10 minutos dependendo da conexão.

### Inicialização Lenta
O airflow-init precisa:
- Migrar banco de dados
- Criar usuário admin
- Inicializar metastore

Aguarde até ver "airflow-init exited with code 0" nos logs.

## 🔍 Verificação

```bash
# Status dos containers
docker compose ps

# Health check
make health

# Testar Airflow diretamente
curl http://localhost:18080/health
```

## 📚 Referências

- [Airflow 2.10.4 Release Notes](https://airflow.apache.org/docs/apache-airflow/2.10.4/release_notes.html)
- [Docker Compose for Airflow](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html)

---

**Data da Atualização**: 2025-11-18
**Versão Anterior**: apache/airflow:latest (instável)
**Versão Atual**: apache/airflow:2.10.4 (LTS)
