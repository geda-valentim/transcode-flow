# 🔌 Transcode Flow - Mapeamento de Portas

Todas as portas foram configuradas no range **1xxxx** para evitar conflitos.

---

## 📋 Lista de Portas

| Serviço | Porta Interna | Porta Externa | URL de Acesso |
|---------|---------------|---------------|---------------|
| **NGINX HTTP** | 80 | **10080** | http://localhost:10080 |
| **NGINX HTTPS** | 443 | **10443** | https://localhost:10443 |
| **Grafana** | 3000 | **13000** | http://localhost:13000 |
| **PostgreSQL** | 5432 | **15432** | localhost:15432 |
| **Flower** | 5555 | **15555** | http://localhost:15555 |
| **Redis** | 6379 | **16379** | localhost:16379 |
| **FastAPI** | 8000 | **18000** | http://localhost:18000 |
| **Airflow** | 8080 | **18080** | http://localhost:18080 |
| **MinIO API** | 9000 | **19000** | http://localhost:19000 |
| **MinIO Console** | 9001 | **19001** | http://localhost:19001 |
| **Prometheus** | 9090 | **19090** | http://localhost:19090 |
| **Alertmanager** | 9093 | **19093** | http://localhost:19093 |
| **Node Exporter** | 9100 | **19100** | http://localhost:19100/metrics |
| **Redis Exporter** | 9121 | **19121** | http://localhost:19121/metrics |
| **Postgres Exporter** | 9187 | **19187** | http://localhost:19187/metrics |

---

## 🌐 Principais Acessos

### Aplicação e API
```bash
# API Documentation (Swagger)
http://localhost:10080/docs

# API Health Check
curl http://localhost:10080/health

# FastAPI Direto (sem NGINX)
http://localhost:18000
```

### Monitoramento
```bash
# Airflow Web UI
http://localhost:18080
# Login: admin / (senha do .env)

# Flower (Celery Monitoring)
http://localhost:15555
# Login: admin / (senha do .env)

# Grafana Dashboards
http://localhost:13000
# Login: admin / (senha do .env)

# Prometheus
http://localhost:19090
```

### Storage
```bash
# MinIO Console
http://localhost:19001
# Login: admin / (senha do .env)

# MinIO API
http://localhost:19000
```

### Banco de Dados
```bash
# PostgreSQL
psql -h localhost -p 15432 -U transcode_user -d transcode_db

# Redis CLI
redis-cli -h localhost -p 16379
```

---

## 🔥 Firewall Rules

Se estiver usando firewall, libere apenas as portas necessárias:

### Desenvolvimento Local (todas as portas)
```bash
# Ubuntu/Debian
sudo ufw allow 10080/tcp
sudo ufw allow 10443/tcp
sudo ufw allow 13000/tcp
sudo ufw allow 15432/tcp
sudo ufw allow 15555/tcp
sudo ufw allow 16379/tcp
sudo ufw allow 18000/tcp
sudo ufw allow 18080/tcp
sudo ufw allow 19000/tcp
sudo ufw allow 19001/tcp
sudo ufw allow 19090/tcp
sudo ufw allow 19093/tcp
```

### Produção (apenas essenciais)
```bash
# Apenas HTTP/HTTPS público
sudo ufw allow 10080/tcp  # HTTP
sudo ufw allow 10443/tcp  # HTTPS

# Resto deve ser acessado apenas via VPN ou rede interna
```

---

## 🔒 Acesso Remoto Seguro

### Opção 1: SSH Tunnel (Recomendado)
```bash
# Túnel para Grafana
ssh -L 13000:localhost:13000 user@server

# Túnel para Airflow
ssh -L 18080:localhost:18080 user@server

# Agora acesse http://localhost:13000 no seu navegador local
```

### Opção 2: VPN
Configure OpenVPN ou WireGuard para acesso seguro à rede interna.

### Opção 3: NGINX com Autenticação
Já configurado no Sprint 7 com SSL/TLS e autenticação.

---

## 📝 Variáveis de Ambiente

Atualize seu `.env` se necessário:

```bash
# Portas (já configuradas no docker-compose.yml)
POSTGRES_PORT=15432
REDIS_PORT=16379
MINIO_PORT=19000
MINIO_CONSOLE_PORT=19001
AIRFLOW_PORT=18080
GRAFANA_PORT=13000
PROMETHEUS_PORT=19090
NGINX_HTTP_PORT=10080
NGINX_HTTPS_PORT=10443
API_PORT=18000
FLOWER_PORT=15555
```

---

## 🧪 Testes de Conectividade

```bash
# Testar todas as portas
make health

# Ou manualmente:
curl http://localhost:10080/health          # NGINX
curl http://localhost:18000/health          # FastAPI
curl http://localhost:19090/-/healthy       # Prometheus
curl http://localhost:13000/api/health      # Grafana
curl http://localhost:19000/minio/health/live  # MinIO

# PostgreSQL
pg_isready -h localhost -p 15432 -U transcode_user

# Redis
redis-cli -h localhost -p 16379 ping
```

---

## ⚠️ Notas Importantes

1. **NGINX é o ponto de entrada principal**: Use `http://localhost:10080` para acessar a API
2. **Portas internas**: Containers comunicam entre si usando portas internas (ex: postgres:5432)
3. **Portas externas**: Apenas para acesso do host (ex: localhost:15432)
4. **Produção**: Configure SSL/TLS e use porta 443 (veja Sprint 10)

---

**Última Atualização:** 2025-11-18
**Range de Portas:** 10080-19187
