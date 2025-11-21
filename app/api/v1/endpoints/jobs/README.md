# Jobs Endpoints - Estrutura Modular

Este diretório contém os endpoints da API relacionados a jobs de transcodificação, refatorados em módulos menores e mais organizados.

## Estrutura

```
app/api/v1/endpoints/jobs/
├── __init__.py           # Consolida todos os routers
├── validations.py        # Funções de validação compartilhadas
├── creation.py           # Endpoints de criação de jobs
├── management.py         # Endpoints de controle de jobs
├── queries.py            # Endpoints de consulta e busca
├── export.py             # Endpoints de exportação
└── README.md            # Esta documentação
```

## Módulos

### `validations.py`
Funções utilitárias compartilhadas para validação:

- `check_job_permissions()` - Valida permissões da API key
- `check_upload_permissions()` - Valida permissões de upload
- `validate_and_process_upload()` - Valida arquivo enviado
- `validate_filesystem_path()` - Valida arquivo do filesystem
- `parse_metadata()` - Parse e validação de metadata JSON
- `build_job_metadata()` - Constrói metadata completo do job
- `increment_usage_counters()` - Incrementa contadores de uso

### `creation.py`
Endpoints para criação de jobs:

- `POST /upload` - Criar job via upload de arquivo
- `POST /filesystem` - Criar job a partir de arquivo no servidor
- `POST /minio` - Criar job a partir de arquivo no MinIO (não implementado)

### `management.py`
Endpoints para gerenciamento de jobs:

- `GET /{job_id}` - Obter status de um job
- `DELETE /{job_id}` - Deletar um job
- `POST /{job_id}/cancel` - Cancelar um job
- `POST /{job_id}/retry` - Retentar um job falho
- `PATCH /{job_id}/priority` - Atualizar prioridade do job

### `queries.py`
Endpoints para consulta e busca:

- `GET /` - Listar jobs com paginação
- `POST /batch/status` - Obter status de múltiplos jobs
- `GET /search` - Busca avançada de jobs
- `GET /stats` - Estatísticas e métricas dos jobs

### `export.py`
Endpoints para exportação de dados:

- `GET /export` - Exportar jobs em formato JSON ou CSV

## Como Usar

Os endpoints são automaticamente incluídos no router principal através do `__init__.py`. Para usar em outros módulos:

```python
from app.api.v1.endpoints import jobs

# O router já está disponível
app.include_router(jobs.router, prefix="/jobs")
```

## Benefícios da Refatoração

1. **Manutenibilidade**: Cada módulo tem uma responsabilidade clara
2. **Legibilidade**: Arquivos menores (150-300 linhas vs 1069 linhas)
3. **Testabilidade**: Mais fácil testar módulos independentes
4. **Reutilização**: Funções de validação podem ser reutilizadas
5. **Organização**: Estrutura clara por funcionalidade

## Arquivo Original

O arquivo original foi renomeado para `jobs_old.py.backup` para referência.

## Migração

Nenhuma mudança é necessária no código que importa os endpoints. A importação continua funcionando:

```python
from app.api.v1.endpoints import jobs
```

O Python automaticamente usa o `__init__.py` do pacote.
