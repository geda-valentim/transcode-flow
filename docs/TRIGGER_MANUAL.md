# Como Disparar a Pipeline de Transcodificação - Airflow 3

## ⚠️ Nota Importante

Devido a um bug no Airflow 3.1.3 API v2, o disparo automático via script não está funcionando. Use o método manual via interface web.

## 🌐 Método Manual (Interface Web)

### Passo 1: Acesse o Airflow
Abra seu navegador e vá para:
```
http://localhost:18080
```

### Passo 2: Faça Login
- **Usuário:** `admin`
- **Senha:** `CHANGE_ME_AIRFLOW_ADMIN_PASSWORD`

### Passo 3: Acesse a DAG
Clique na DAG `video_transcoding_pipeline` ou acesse diretamente:
```
http://localhost:18080/dags/video_transcoding_pipeline/grid
```

### Passo 4: Dispare a DAG
1. Clique no botão **"Play" (▶)** no canto superior direito
2. Selecione **"Trigger DAG w/ config"**
3. Cole a configuração JSON:

```json
{
  "job_id": "job-20251120-001",
  "video_path": "/data/temp/video.mp4"
}
```

4. Clique em **"Trigger"**

### Passo 5: Acompanhe a Execução
- A DAG começará a executar automaticamente
- Você pode ver o progresso em tempo real na visualização **Graph** ou **Grid**
- Clique em cada task para ver os logs

## 📝 Formato da Configuração

```json
{
  "job_id": "identificador-unico-do-job",
  "video_path": "caminho-completo-do-video"
}
```

### Campos:
- **job_id**: Identificador único para este job (ex: `job-20251120-123456`)
- **video_path**: Caminho completo do vídeo dentro do container (ex: `/data/temp/video.mp4`)

## 📹 Vídeo de Teste

Há um vídeo de teste disponível em:
```
/data/temp/video.mp4
```

Use este caminho na configuração JSON.

## 🔧 Script Automático (Quando o Bug for Corrigido)

Quando o bug do Airflow 3 API v2 for corrigido, você poderá usar:

```bash
python3 trigger_pipeline.py /home/transcode-flow/data/temp/video.mp4
```

## 📊 Monitoramento

Após disparar a DAG, você pode monitorar:

- **Airflow UI**: http://localhost:18080
- **Flower (Celery)**: http://localhost:15555
- **Grafana**: http://localhost:13000
- **Prometheus**: http://localhost:19090

## ❓ Troubleshooting

### DAG não aparece?
- Verifique os logs do scheduler: `docker logs transcode-airflow-scheduler`
- Verifique se a DAG está pausada (toggle na UI)

### Tasks falhando?
- Clique na task que falhou
- Veja os logs clicando em "Log"
- Verifique se todos os serviços estão rodando: `docker compose ps`

### Job não aparece no banco?
- A primeira task da DAG deve criar o job no banco
- Verifique os logs da task `validate_video`

## 📚 Documentação Adicional

- [Airflow 3 Documentation](https://airflow.apache.org/docs/apache-airflow/stable/)
- [Bug Report](./AIRFLOW3_API_BUG.md)
