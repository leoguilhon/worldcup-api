# WorldCup API

API em Python para consultar calendario, placares, status, grupos, classificacao e eventos basicos de jogos da Copa do Mundo 2026.

O projeto foi desenhado como uma API de producao orientada a cache: nenhuma requisicao HTTP de usuario dispara scraping. A API consulta somente o PostgreSQL; a coleta de dados roda em um worker separado, que busca HTML publico, interpreta os dados com BeautifulSoup e atualiza o banco.

## Destaques

- FastAPI com documentacao OpenAPI em `/docs`.
- PostgreSQL como fonte unica da API.
- Worker separado para scraping e atualizacao de placares.
- Scraping com `requests` + `BeautifulSoup4`, sem APIs externas pagas ou gratuitas.
- Calendario da Copa 2026 via HTML da Wikipedia.
- Placar/status via HTML da ESPN scoreboard.
- Rastreamento opcional de amistosos pre-Copa.
- Atualizacao de jogos ao vivo com alvo de aproximadamente 60 segundos.
- Suporte a `LIVE`, `HALF_TIME`, `EXTRA_TIME`, `PENALTIES`, `FINISHED` e outros status.
- Classificacao de grupos ja inicializada com selecoes zeradas antes dos jogos.
- Eventos de gol quando a ESPN expoe autores e minutos no HTML.
- Observabilidade com `/scraping/status`, `scrape_runs` e heartbeat do worker.
- Docker, docker-compose, Alembic, Pydantic e SQLAlchemy.

## Arquitetura

```text
Usuario / Cliente
      |
      v
FastAPI
      |
      v
PostgreSQL  <------------- Worker de Scraping
      ^                         |
      |                         v
      |                  Fontes HTML publicas
      |                  - Wikipedia 2026
      |                  - ESPN scoreboard
```

### Principio central

```text
Request HTTP da API nunca faz scraping.
```

Isso evita lentidao, bloqueios, instabilidade de terceiros e consumo agressivo das fontes. O worker coleta dados em intervalos controlados e salva tudo no banco. A API responde rapido lendo dados ja persistidos.

## Stack

- Python 3.12+
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- BeautifulSoup4
- requests
- python-dotenv
- Docker e docker-compose

## Estrutura

```text
app/
|-- main.py
|-- database.py
|-- config.py
|-- models/
|-- schemas/
|-- routers/
|-- services/
|-- workers/
`-- utils/

alembic/
tests/
examples/
docker-compose.yml
docker-compose.prod.yml
Dockerfile
requirements.txt
```

## Modelagem Principal

### Team

Representa selecoes e times encontrados nas fontes.

Campos relevantes:

```text
name
country_code
flag_url
is_placeholder
created_at
updated_at
```

`is_placeholder=true` identifica nomes de mata-mata ainda indefinidos, como `Winner Group A` ou `Runner-up Group C`.

### Match

Representa jogos da Copa e amistosos rastreados.

Campos relevantes:

```text
external_id
espn_event_id
competition
source_url
home_team
away_team
stadium
city
group_name
stage
match_date
status
status_detail
home_score
away_score
home_penalty_score
away_penalty_score
minute
winner_team
last_scraped_at
scrape_status
```

`competition` pode ser:

```text
WORLD_CUP
FRIENDLY
```

`status` pode ser:

```text
SCHEDULED
LIVE
HALF_TIME
EXTRA_TIME
PENALTIES
FINISHED
POSTPONED
CANCELLED
UNKNOWN
```

### MatchEvent

Representa eventos persistidos de uma partida.

Atualmente, com a fonte ESPN scoreboard, o projeto registra gols quando o HTML expoe autores e minutos. O modelo tambem suporta outros tipos de evento, como cartoes, substituicoes e VAR, caso uma fonte futura exponha esses dados.

### ScrapeRun

Historico operacional das execucoes de scraping.

Campos relevantes:

```text
source
status
started_at
finished_at
parsed_count
applied_count
error_message
```

### WorkerHeartbeat

Registra o ultimo sinal de vida do worker.

Usado por `/scraping/status` para informar se o worker parece saudavel.

## Como Rodar em Desenvolvimento

1. Crie o `.env`:

```bash
cp .env.example .env
```

2. Suba banco, API e worker:

```bash
docker compose up --build
```

3. Em outro terminal, aplique as migrations:

```bash
docker compose exec api alembic upgrade head
```

4. Sincronize o calendario da Copa:

```bash
docker compose exec api python -m app.workers.sync_schedule_once
```

5. Sincronize placares/status uma vez:

```bash
docker compose exec api python -m app.workers.sync_live_once
```

6. Opcionalmente, rastreie amistosos pre-Copa:

```bash
docker compose exec api python -m app.workers.sync_friendlies_once
```

7. Acesse:

```text
API:  http://localhost:8000
Docs: http://localhost:8000/docs
Health: http://localhost:8000/health
```

## Como Rodar em Producao

Use senhas fortes no `.env`:

```env
DATABASE_URL=postgresql+psycopg://worldcup:SENHA_FORTE@db:5432/worldcup
POSTGRES_DB=worldcup
POSTGRES_USER=worldcup
POSTGRES_PASSWORD=SENHA_FORTE
CORS_ALLOWED_ORIGINS=https://seu-front-end.com
```

Suba a stack sem bind mount e sem reload:

```bash
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
docker compose -f docker-compose.prod.yml exec api python -m app.workers.sync_schedule_once
docker compose -f docker-compose.prod.yml exec api python -m app.workers.sync_friendlies_once
docker compose -f docker-compose.prod.yml exec api python -m app.workers.sync_live_once
```

Se voce ja tinha um volume antigo criado com outro nome de banco, crie o banco/usuario `worldcup` no Postgres existente ou recrie o volume. Depois rode `alembic upgrade head` e as sincronizacoes acima para garantir o schema e os dados atualizados.

Verifique os servicos:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
curl http://localhost:8000/health/db
curl http://localhost:8000/scraping/status
```

Acompanhe logs:

```bash
docker compose -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.prod.yml logs -f api
```

## Endpoints

### Health e Observabilidade

```http
GET /health
GET /health/db
GET /scraping/status
```

`/scraping/status` retorna:

```text
status geral: ok, degraded ou unknown
worker_status
ultimo heartbeat do worker
ultimo scrape bem-sucedido
ultimas execucoes em scrape_runs
jogos ativos sem update ha mais de 90s
contagem de jogos ativos
```

### Times

```http
GET /teams
GET /teams/{team_id}
```

Por padrao, `/teams` retorna somente selecoes reais.

Para incluir placeholders do mata-mata:

```bash
curl "http://localhost:8000/teams?include_placeholders=true"
```

### Jogos

```http
GET /matches
GET /matches/today
GET /matches/live
GET /matches/{match_id}
GET /matches/{match_id}/events
```

Filtros de `/matches`:

```text
status
competition
group_name
stage
date
```

Exemplos:

```bash
curl "http://localhost:8000/matches?status=LIVE"
curl "http://localhost:8000/matches?competition=FRIENDLY"
curl "http://localhost:8000/matches?competition=WORLD_CUP&group_name=A"
curl "http://localhost:8000/matches?date=2026-06-11"
```

`status=LIVE` retorna jogos em andamento, incluindo:

```text
LIVE
HALF_TIME
EXTRA_TIME
PENALTIES
```

### Eventos

```http
GET /matches/{match_id}/events
```

Retorna eventos persistidos daquele jogo. Com a fonte ESPN atual, o projeto registra gols quando a scoreboard HTML fornece a lista de autores e minutos.

Exemplo de resposta:

```json
[
  {
    "id": 7,
    "match_id": 155,
    "team_id": 135,
    "player_name": "T. Atcheson",
    "event_type": "GOAL",
    "minute": 9,
    "extra_minute": null
  }
]
```

### Grupos

```http
GET /groups
GET /groups/{group_name}/standings
```

`/groups/{group_name}/standings` ja retorna as selecoes do grupo antes dos jogos, com pontuacao zerada. Conforme jogos `FINISHED` entram no banco, a tabela recalcula:

```text
played
won
drawn
lost
goals_for
goals_against
goal_difference
points
```

Exemplo:

```bash
curl http://localhost:8000/groups/A/standings
```

## Worker de Scraping

O worker principal roda com:

```bash
python -m app.workers.live_score_worker
```

Comandos one-shot:

```bash
python -m app.workers.sync_schedule_once
python -m app.workers.sync_live_once
python -m app.workers.sync_friendlies_once
```

Responsabilidades:

```text
scrape_schedule        -> calendario da Copa
scrape_live_matches    -> placares/status de jogos candidatos
discover_friendlies    -> amistosos pre-Copa envolvendo times monitorados
```

O worker prioriza placar ao vivo. Enquanto houver jogo ativo, ele evita rodar tarefas pesadas de calendario/descoberta no mesmo ciclo.

## Fontes de Dados

### Wikipedia

Usada para montar o calendario base da Copa 2026:

```text
https://en.wikipedia.org/wiki/2026_FIFA_World_Cup
```

O parser le blocos HTML `footballbox` para extrair jogos, times, grupos, datas, estagios, estadios e cidades.

### ESPN

Usada para placar/status ao vivo:

```text
https://www.espn.com/soccer/scoreboard/_/league/fifa.world
https://www.espn.com/soccer/scoreboard/_/league/fifa.friendly
```

A ESPN embute estado inicial dos jogos no HTML. O parser le esse estado e atualiza:

```text
espn_event_id
status
status_detail
placar
minuto
estadio
cidade
eventos de gol
vencedor
source_url
last_scraped_at
scrape_status
```

## Scraping Etico

O projeto foi implementado com cuidado para evitar scraping agressivo:

- nao usa proxy rotativo;
- nao burla bloqueios;
- consulta `robots.txt`;
- usa `User-Agent` configuravel;
- aplica timeout;
- aplica intervalo minimo entre requisicoes;
- usa backoff simples em erro HTTP;
- registra falhas com `scrape_status` e `scrape_runs`.

Antes de usar qualquer fonte em producao, revise os termos de uso, `robots.txt` e a frequencia permitida.

## Configuracao

Principais variaveis:

```env
APP_NAME=WorldCup API
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://worldcup:worldcup@db:5432/worldcup
CORS_ALLOWED_ORIGINS=https://seu-front-end.com

SCRAPER_USER_AGENT=WorldCupBot/1.0 (+https://example.com/bot)
SCRAPER_TIMEOUT_SECONDS=10
SCRAPER_MIN_REQUEST_INTERVAL_SECONDS=5

SCHEDULE_SCRAPE_INTERVAL_HOURS=6
LIVE_SCRAPE_INTERVAL_SECONDS=60

SOURCE_PROVIDER=wikipedia_2026
SOURCE_SCHEDULE_URL=https://en.wikipedia.org/wiki/2026_FIFA_World_Cup

LIVE_SCORE_PROVIDER=espn_worldcup
ESPN_SCOREBOARD_URL=https://www.espn.com/soccer/scoreboard/_/league/fifa.world
ESPN_FRIENDLY_SCOREBOARD_URL=https://www.espn.com/soccer/scoreboard/_/league/fifa.friendly

FRIENDLY_TRACKING_ENABLED=true
FRIENDLY_TRACKING_START_DATE=2026-06-01
FRIENDLY_TRACKING_END_DATE=2026-06-10
FRIENDLY_DISCOVERY_INTERVAL_HOURS=12

LIVE_SCORE_WINDOW_BEFORE_MINUTES=180
LIVE_SCORE_WINDOW_AFTER_MINUTES=240
```

## Testes

### Unitarios

Usam HTML mockado da ESPN e SQLite em memoria:

```bash
docker compose exec api python -m tests.run_unit_tests
```

Cobrem:

```text
parser ESPN
status LIVE/HALF_TIME/EXTRA_TIME/PENALTIES/FINISHED
placar de penaltis quando exposto
eventos de gol
country_code e placeholders
standings com times zerados
descoberta de amistosos
targets de scraping por competicao
scraping/status com heartbeat e scrape run
```

### Integrados

Rodam contra a stack real em `localhost:8000`:

```bash
docker compose -f docker-compose.prod.yml exec api python -m tests.run_integration_tests
```

Validam:

```text
/health
/health/db
/groups
/groups/A/standings
/matches/live
/scraping/status
```

### Simulacao de Standings

Simula resultados e faz rollback:

```bash
docker compose exec api python -m app.workers.simulate_group_standings_once
```

### Teste Real de Parser ESPN

Valida um evento especifico sem gravar no banco:

```bash
docker compose exec api python -m app.workers.validate_espn_event_once
```

## Observabilidade

O projeto possui tres camadas de observabilidade:

1. Logs de console da API e worker.
2. Tabela `scrape_runs`, com historico de execucoes.
3. Endpoint `/scraping/status`, com leitura operacional consolidada.

Exemplo:

```bash
curl http://localhost:8000/scraping/status
```

Resposta resumida:

```json
{
  "status": "ok",
  "worker_status": "ok",
  "active_matches_count": 2,
  "stale_active_matches_count": 0,
  "last_success_at": "2026-06-04T19:41:17.831450Z"
}
```

## Limitacoes Conhecidas

- O projeto depende de HTML publico. Se ESPN ou Wikipedia mudarem a estrutura, o parser pode precisar de ajuste.
- O placar de disputa de penaltis so e preenchido quando a ESPN expoe esse campo no HTML da scoreboard.
- Eventos completos como cartoes, substituicoes e VAR dependem da fonte expor esses dados. Hoje, o fluxo confiavel registra gols.
- Plano gratuito de hospedagem pode dormir ou suspender worker; para jogos ao vivo, o worker precisa ficar ativo.
- Para producao critica, recomenda-se uma segunda fonte de validacao como fallback.

## Proximos Passos

- Adicionar scraper da pagina detalhada do jogo para eventos mais completos.
- Implementar fonte fallback para placar final.
- Criar alertas externos para `/scraping/status`.
- Expor metricas Prometheus/OpenTelemetry.
- Adicionar testes end-to-end com banco limpo em pipeline CI.

## Decisoes Tecnicas

- API sem scraping em request para manter baixa latencia.
- PostgreSQL como cache persistente e fonte unica de leitura.
- Worker separado para controle de frequencia e tratamento de falhas.
- BeautifulSoup para parsing HTML puro, sem depender de API externa.
- Alembic para evolucao segura do schema.
- Status operacional persistido para facilitar diagnostico em producao.

## Rodando Localmente Sem Docker

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.workers.sync_schedule_once
python -m app.workers.sync_friendlies_once
python -m app.workers.sync_live_once
uvicorn app.main:app --reload
```

Worker em outro terminal:

```bash
python -m app.workers.live_score_worker
```

## Licenca e Uso

Este projeto e uma implementacao educacional/portfolio para demonstrar arquitetura com FastAPI, PostgreSQL, workers e scraping responsavel. Ao publicar ou operar em producao, revise os termos de uso das fontes utilizadas.
