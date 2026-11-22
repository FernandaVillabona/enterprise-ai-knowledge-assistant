# Enterprise AI Knowledge Assistant

Asistente empresarial con **RAG (Retrieval-Augmented Generation)**: una empresa sube sus documentos (PDF, DOCX, TXT) y los empleados hacen preguntas en lenguaje natural. La IA responde **solo** con la información recuperada de esos documentos y **cita las fuentes** (documento y página).

> 🚧 Proyecto en construcción por fases. Ver [Hoja de ruta](#hoja-de-ruta).

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Angular |
| API | Python · FastAPI |
| Base de datos | PostgreSQL 16 + **pgvector** |
| IA | OpenAI API (chat + embeddings) |
| Infra | Docker Compose |

## Arquitectura

```mermaid
flowchart LR
    U[Usuario] --> FE[Angular]
    FE -->|JWT| API[FastAPI]
    API --> PG[(PostgreSQL + pgvector)]
    API --> OAI[OpenAI API]

    subgraph Ingesta
      D[PDF/DOCX/TXT] --> P[Extraer texto por página] --> C[Chunking] --> E[Embeddings] --> PG
    end

    subgraph Consulta
      Q[Pregunta] --> QE[Embedding] --> VS[Búsqueda vectorial<br/>filtrada por permisos] --> CTX[Contexto + prompt] --> LLM[Respuesta con citas] --> EV[Evaluación de fidelidad]
    end
```

### Flujo de una pregunta

1. El usuario pregunta: *«¿Cuántos días de vacaciones me corresponden?»*
2. Se calcula el embedding de la pregunta.
3. pgvector devuelve los fragmentos más similares **solo de documentos que el usuario tiene permiso para ver**.
4. Los fragmentos se envían al modelo junto con instrucciones de responder únicamente con ese contexto.
5. La respuesta incluye citas `[documento, página]` y una puntuación de fidelidad (detección de alucinaciones).

## Hoja de ruta

- [x] **Fase 0 – Fundamentos**: estructura del repo, Docker Compose, PostgreSQL + pgvector, FastAPI con `/api/health`.
- [x] **Fase 1 – Autenticación**: modelo de usuario, Alembic, registro/login con JWT, hash bcrypt, rol admin/user, tests.
- [x] **Fase 2 – Ingesta de documentos**: subida (admin), extracción PDF/DOCX/TXT por página, chunking por tokens con solapamiento, embeddings en lote, procesamiento en segundo plano.
- [x] **Fase 3 – Búsqueda semántica**: índice HNSW (coseno), full-text en español (GIN), búsqueda híbrida con RRF, tests contra PostgreSQL real en CI.
- [x] **Fase 4 – Chat RAG**: conversaciones con historial, reescritura de preguntas de seguimiento, prompt con fuentes delimitadas, citas validadas.
- [x] **Fase 5 – Roles y permisos**: grupos, documentos públicos/restringidos (denegar por defecto), filtro de permisos dentro de la consulta de recuperación, historial que respeta accesos revocados.
- [ ] **Fase 6 – Evaluación**: verificación de fidelidad (LLM-as-judge), dataset de evaluación, métricas.
- [ ] **Fase 7 – Frontend Angular**: login, chat, panel de administración.
- [ ] **Fase 8 – Calidad**: tests, CI con GitHub Actions, despliegue.

## Puesta en marcha

### Requisitos

- Docker Desktop
- Python 3.12+ (para desarrollo local sin Docker)
- Node.js 20+ (para el frontend, fase 7)

### Con Docker

```bash
cp .env.example .env      # y rellena OPENAI_API_KEY
docker compose up --build
```

Abre http://localhost:8000/docs (Swagger) y prueba `GET /api/health`:

```json
{ "status": "ok", "database": "ok", "pgvector": "0.8.0" }
```

### Backend en local (BD en Docker)

```bash
docker compose up -d db
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements-dev.txt
alembic upgrade head            # crea las tablas
uvicorn app.main:app --reload
```

### Crear un administrador

El registro público (`POST /api/auth/register`) siempre crea usuarios con rol `user`. Los administradores se crean por consola:

```bash
python -m app.scripts.create_admin --email admin@empresa.com --name "Admin"
# o con Docker:
docker compose exec backend python -m app.scripts.create_admin --email admin@empresa.com --name "Admin"
```

### Tests

```bash
cd backend
pytest -q
```

## API (hasta ahora)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/health` | – | Estado de la API, la BD y pgvector |
| POST | `/api/auth/register` | – | Registro (rol `user`) |
| POST | `/api/auth/login` | – | Login (form `username`=email, `password`) → JWT |
| GET | `/api/auth/me` | Bearer | Usuario autenticado |
| POST | `/api/documents` | Admin | Subir PDF/DOCX/TXT (multipart `file`, `title`, `visibility`, `group_ids`) → 202 |
| GET | `/api/documents` | Admin | Listar documentos y su estado |
| GET | `/api/documents/accessible` | Bearer | Documentos que puedo consultar |
| PUT | `/api/documents/{id}/access` | Admin | Cambiar `visibility` y `group_ids` |
| GET | `/api/documents/{id}` | Admin | Estado: `pending` → `processing` → `ready` / `failed` |
| GET | `/api/documents/{id}/chunks` | Admin | Ver cómo se ha troceado el documento |
| POST | `/api/documents/{id}/reprocess` | Admin | Volver a procesar |
| DELETE | `/api/documents/{id}` | Admin | Borrar documento, chunks y archivo |
| POST | `/api/search` | Bearer | Búsqueda `{query, top_k, mode: semantic\|keyword\|hybrid, min_similarity}` |
| POST | `/api/conversations` | Bearer | Crear conversación |
| GET | `/api/conversations` | Bearer | Mis conversaciones (más recientes primero) |
| GET | `/api/conversations/{id}` | Bearer | Conversación con mensajes y fuentes |
| DELETE | `/api/conversations/{id}` | Bearer | Borrar conversación |
| POST | `/api/conversations/{id}/messages` | Bearer | Preguntar → respuesta con citas y fuentes |
| POST/GET | `/api/groups` | Admin | Crear / listar grupos (con miembros) |
| PATCH/DELETE | `/api/groups/{id}` | Admin | Renombrar / borrar grupo |
| PUT | `/api/groups/{id}/members` | Admin | Reemplazar miembros `{user_ids}` |
| GET | `/api/users` | Admin | Usuarios con sus grupos |
| PATCH | `/api/users/{id}` | Admin | Cambiar `role`, `is_active`, `group_ids` |

## Control de acceso

| | Documento `public` | `restricted` con grupos | `restricted` sin grupos |
|---|---|---|---|
| Admin | ✅ | ✅ | ✅ |
| Usuario miembro de alguno de sus grupos | ✅ | ✅ | ❌ |
| Resto de usuarios | ✅ | ❌ | ❌ |

- **El filtro va en la consulta SQL de recuperación** (`services/permissions.py`), como un `EXISTS` sobre las tablas de grupos. Un fragmento no autorizado nunca sale de la base de datos y, por tanto, nunca llega al prompt. Filtrar después, o pedirle al LLM que «no use» ciertos documentos, no es seguro.
- **El parámetro `access` de la búsqueda es obligatorio**: olvidarlo es un error de programación, no una fuga silenciosa.
- **Denegar por defecto**: los documentos nuevos (y los existentes al migrar) son `restricted` sin grupos, visibles solo para admins.
- **Permisos evaluados al leer**: si un usuario pierde acceso a un documento, las fuentes guardadas en su historial se ocultan y las respuestas basadas en él no se reenvían al modelo como contexto.
- **HNSW + filtros**: `hnsw.iterative_scan` evita que el filtro de permisos deje la búsqueda vectorial con menos resultados de los pedidos.

## Cómo funciona la ingesta

```mermaid
flowchart LR
    A[Subida] -->|valida extensión,<br/>firma y tamaño| B[(Disco)]
    B --> C[Extraer texto<br/>por página]
    C --> D[Chunks de ~500 tokens<br/>solape 80, sin cruzar páginas]
    D --> E[Embeddings en lotes<br/>título + chunk]
    E --> F[(chunks + vector 1536)]
```

Decisiones de diseño:

- **Por página**: cada chunk guarda su `page_number`; es lo que permite citar «documento, pág. N».
- **Tokens, no caracteres**: el tamaño se mide con `tiktoken` (`cl100k_base`), el tokenizador de los modelos de embeddings de OpenAI.
- **Fronteras naturales**: se corta por párrafo → frase → tokens, con solapamiento para no perder ideas que caen en el corte.
- **Título en el embedding**: se embebe `título + chunk`, para que un fragmento que no menciona el tema (p. ej. «son 23 días hábiles») siga siendo recuperable.
- **Seguridad en la subida**: se comprueba la firma del archivo (magic bytes), no solo la extensión; el nombre en disco es un UUID; hay límite de tamaño.
- **Segundo plano**: la subida responde 202 al instante y el procesamiento corre en `BackgroundTasks`. En producción usaría una cola (Celery/RQ) con reintentos.

## Cómo funciona la búsqueda

| Modo | Cómo | Bueno para | Falla con |
|---|---|---|---|
| `semantic` | Distancia coseno entre embeddings (`<=>`, índice HNSW) | Sinónimos, paráfrasis («días libres» → vacaciones) | Códigos y términos exactos («ISO-27001») |
| `keyword` | Full-text de PostgreSQL en español (`websearch_to_tsquery`, índice GIN) | Términos exactos, con stemming («reembolso» → «reembolsan») | Sinónimos |
| `hybrid` *(por defecto)* | Ambas + **Reciprocal Rank Fusion**: `score = Σ 1/(60 + posición)` | Lo mejor de las dos | — |

- **HNSW** es un índice de vecinos *aproximados*: navega un grafo en vez de comparar con todos los vectores. `hnsw.ef_search` regula el equilibrio velocidad/recall.
- **Escaneo iterativo** (`hnsw.iterative_scan`, pgvector ≥ 0.8): con filtros (`WHERE`), HNSW podría devolver menos de `top_k` filas porque filtra después de elegir candidatos. Será clave al filtrar por permisos en la fase 5.
- **RRF** fusiona por *posición*, así no hay que normalizar puntuaciones de escalas distintas (coseno 0..1 vs `ts_rank`).

## Cómo funciona el chat RAG

```mermaid
sequenceDiagram
    participant U as Usuario
    participant API as FastAPI
    participant LLM as OpenAI
    participant DB as pgvector
    U->>API: «¿Y los becarios?»
    API->>LLM: Reescribe con el historial
    LLM-->>API: «días de vacaciones de los becarios»
    API->>DB: Búsqueda híbrida (top 6)
    DB-->>API: Fragmentos + documento + página
    alt sin resultados relevantes
        API-->>U: «No he encontrado información…» (sin llamar al LLM)
    else
        API->>LLM: Reglas + fuentes numeradas + historial + pregunta
        LLM-->>API: Respuesta con [1][2]
        API->>API: Valida citas (elimina las que no existen)
        API-->>U: Respuesta + fuentes (cited=true/false)
    end
```

- **Grounding**: el *system prompt* obliga a responder solo con las fuentes y a usar una frase fija cuando no está la respuesta.
- **Fuentes delimitadas** con `<fuente id="n" documento="…" pagina="…">`, y la instrucción de tratarlas como datos: mitiga la *prompt injection* desde documentos.
- **Reescritura de la pregunta**: las preguntas de seguimiento («¿y eso?») se convierten en consultas autónomas antes de buscar.
- **Sin contexto, sin LLM**: si la recuperación no encuentra nada relevante se responde directamente; más barato y sin riesgo de inventar.
- **Validación de citas**: una cita a una fuente que no se envió es una alucinación; se elimina de la respuesta y se registra.
- **Trazabilidad**: cada respuesta guarda la consulta usada, las fuentes (citadas o no), el modelo, los tokens y la latencia; es la base de la evaluación de la fase 6.

### Tests contra PostgreSQL

Los tests marcados `@pytest.mark.postgres` se omiten con SQLite. Para ejecutarlos:

```powershell
docker compose up -d db
docker compose exec db createdb -U kb_user kb_test
$env:TEST_DATABASE_URL = "postgresql+psycopg://kb_user:kb_password@localhost:5432/kb_test"
pytest -q
```

En GitHub Actions ([backend-tests.yml](.github/workflows/backend-tests.yml)) se ejecutan siempre, con un servicio `pgvector/pgvector:0.8.0-pg16`, y además se prueban las migraciones arriba y abajo.

En Swagger (`/docs`) usa el botón **Authorize** para hacer login y probar las rutas protegidas.

## Estructura

```
.
├── backend/
│   ├── app/
│   │   ├── api/          # Routers de FastAPI y dependencias (auth, roles)
│   │   ├── core/         # Configuración, seguridad (bcrypt, JWT)
│   │   ├── db/           # Conexión a la BD
│   │   ├── models/       # Modelos ORM (SQLAlchemy)
│   │   ├── schemas/      # Esquemas Pydantic (entrada/salida de la API)
│   │   ├── scripts/      # Utilidades de consola (create_admin)
│   │   ├── services/     # Lógica: extracción, chunking, embeddings, ingesta, búsqueda, LLM, RAG
│   │   └── main.py
│   ├── migrations/       # Migraciones Alembic
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── db/init/              # SQL de inicialización (activa pgvector)
├── docker-compose.yml
└── .env.example
```
