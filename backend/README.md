# Backend Alinia

Base COM-02 com Python 3.12, FastAPI, SQLAlchemy e Alembic. Execute os comandos na raiz do repositório. Em PowerShell:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock.txt
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini upgrade head
backend/.venv/Scripts/python -m uvicorn backend.app.main:create_app --factory --reload
```

Em Linux/macOS use `backend/.venv/bin/python` no lugar do caminho acima. A configuração padrão usa SQLite local (`alinia.db` na raiz, ignorado pelo Git). Abra `http://127.0.0.1:8000/health` e `http://127.0.0.1:8000/docs`; o OpenAPI está em `/openapi.json`. O health confirma que o processo responde, não a disponibilidade do banco. Migrações são explícitas e não rodam na inicialização.

Para PostgreSQL, configure `DATABASE_URL` no ambiente antes das migrações e do servidor, no formato SQLAlchemy `postgresql+psycopg://usuario:senha@host:5432/banco`; faça percent-encoding de caracteres especiais na senha. Use credenciais locais ou um gerenciador de segredos, sem gravá-las no repositório. Exemplo PowerShell sem valor: `$env:DATABASE_URL = '<URL fornecida pelo ambiente>'`. Para voltar ao SQLite remova a variável. SQLite é destinado a desenvolvimento e testes.

```powershell
backend/.venv/Scripts/python -m pytest backend/tests
```

## Extensão

Cada domínio declara um `DomainModule` em `app/core/modules.py`, com seus `APIRouter`s e `JobDefinition`s, e o adiciona a `DOMAIN_MODULES`. O registro apenas disponibiliza definições em `app.state.jobs`: não agenda nem executa trabalhos; fila, worker e recuperação pertencem a P1-07. Nomes duplicados são rejeitados. Cada aplicação possui configuração, engine, fábrica de sessões e registro próprios. Use `app.state.session_factory` para criar sessões de curta duração e fechá-las após o uso.

Modelos futuros herdam de `Base` em `app/core/database.py`; importe os módulos de modelos em `migrations/env.py` antes de gerar revisões. Gere com `python -m alembic -c backend/alembic.ini revision --autogenerate -m "descricao"`, revise o arquivo e aplique com `upgrade head`. A revisão inicial é uma baseline vazia; cada domínio cria sua própria migração. Autenticação, autorização e auditoria pertencem a P2-01 e ainda não existem; esta base não expõe dados de domínio.
