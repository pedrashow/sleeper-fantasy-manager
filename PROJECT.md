# Sleeper Fantasy Manager

Plataforma pessoal de gestão de ligas de fantasy football integrada ao Sleeper e alimentada por rankings do FantasyPros.

---

## Visão Geral

O projeto atende um único usuário que gerencia múltiplas ligas dynasty no Sleeper. O objetivo é centralizar informações espalhadas entre o app do Sleeper, planilhas e sites de rankings em uma interface unificada que responda três perguntas recorrentes:

1. **Quem eu drafto?** (Draft)
2. **O que meu time precisa e como consigo?** (Roster Intelligence)
3. **Quem eu escalo e como estou indo?** (Matchup & Lineup)

---

## Premissas Técnicas

| Item | Decisão |
|---|---|
| Plataforma de ligas | Sleeper (exclusivo) |
| Fonte de rankings | FantasyPros (ECR, ADP, projeções semanais) |
| API do Sleeper | Pública, sem autenticação, read-only (`requests`) |
| Dados do FantasyPros | Scraping automatizado via scripts Python locais (`requests` + `BeautifulSoup`) |
| UI | Streamlit (app local, tudo em Python) |
| Banco de dados | SQLite (arquivo único `data/fantasy.db`, acesso via `sqlite3` ou `sqlalchemy`) |
| Automação | Makefile + cron para atualização de rankings |
| Multi-liga | O usuário pode ter N ligas; sidebar permite alternar entre elas |
| Linguagem | Python 3.11+ (único stack, sem frontend separado) |

### Estrutura do Projeto

```
sleeper-fantasy-manager/
├── app/
│   ├── pages/              ← Streamlit pages (multi-page app)
│   │   ├── 1_draft.py
│   │   ├── 2_roster.py
│   │   ├── 3_trades.py
│   │   ├── 4_waivers.py
│   │   └── 5_matchup.py
│   └── Home.py             ← Entry point, seleção de liga
├── core/
│   ├── sleeper.py           ← Client da API do Sleeper
│   ├── db.py                ← SQLite setup, queries, models
│   └── rankings.py          ← Leitura e parsing dos rankings
├── scrapers/
│   ├── fantasypros.py       ← Scraping de rankings
│   └── sync_sleeper.py      ← Sync rosters/matchups do Sleeper → SQLite
├── data/
│   ├── fantasy.db           ← SQLite database
│   └── rankings/            ← JSONs cacheados dos scrapers
├── Makefile
├── requirements.txt
└── README.md
```

### Schema SQLite (tabelas principais)

```sql
-- Ligas do usuário
CREATE TABLE leagues (
    league_id TEXT PRIMARY KEY,
    name TEXT,
    season TEXT,
    league_type TEXT,          -- 'dynasty' | 'keeper' | 'redraft' (derivado de settings.type)
    scoring_type TEXT,         -- 'ppr' | 'half_ppr' | 'standard' (derivado de scoring_settings.rec)
    is_superflex INTEGER,      -- 1 se SUPER_FLEX in roster_positions
    is_tep INTEGER,            -- 1 se scoring_settings.bonus_rec_te > 0
    has_kicker INTEGER,        -- 1 se 'K' in roster_positions
    has_dst INTEGER,           -- 1 se 'DEF' in roster_positions
    roster_positions TEXT,     -- JSON array (mantido para referência completa)
    scoring_settings TEXT,     -- JSON blob (mantido para cálculos de projeção)
    total_rosters INTEGER,
    draft_id TEXT,
    draft_rounds INTEGER,
    taxi_slots INTEGER DEFAULT 0,
    reserve_slots INTEGER DEFAULT 0,
    updated_at TIMESTAMP
);

-- Donos/managers
CREATE TABLE users (
    user_id TEXT,
    league_id TEXT,
    display_name TEXT,
    team_name TEXT,
    avatar TEXT,
    roster_id INTEGER,
    PRIMARY KEY (user_id, league_id)
);

-- Rosters atuais
CREATE TABLE rosters (
    roster_id INTEGER,
    league_id TEXT,
    owner_id TEXT,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    fpts REAL DEFAULT 0,
    waiver_position INTEGER,
    waiver_budget_used INTEGER DEFAULT 0,
    updated_at TIMESTAMP,
    PRIMARY KEY (roster_id, league_id)
);

-- Jogadores em cada roster (normalizado)
CREATE TABLE roster_players (
    league_id TEXT,
    roster_id INTEGER,
    player_id TEXT,
    slot TEXT,                -- 'starter', 'bench', 'taxi', 'reserve'
    PRIMARY KEY (league_id, roster_id, player_id)
);
CREATE INDEX idx_rp_player ON roster_players(player_id);
CREATE INDEX idx_rp_league ON roster_players(league_id);

-- Base de jogadores (cache do /players/nfl)
CREATE TABLE players (
    player_id TEXT PRIMARY KEY,
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    position TEXT,
    team TEXT,
    age INTEGER,
    status TEXT,
    injury_status TEXT,
    years_exp INTEGER,
    updated_at TIMESTAMP
);

-- Picks de draft
CREATE TABLE draft_picks (
    draft_id TEXT,
    pick_no INTEGER,
    round INTEGER,
    roster_id INTEGER,
    player_id TEXT,
    player_name TEXT,
    position TEXT,
    team TEXT,
    picked_by TEXT,
    PRIMARY KEY (draft_id, pick_no)
);

-- Transações (trades, waivers, adds/drops)
CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    league_id TEXT,
    type TEXT,                -- 'trade', 'waiver', 'free_agent'
    status TEXT,
    week INTEGER,
    roster_ids TEXT,          -- JSON array
    adds TEXT,                -- JSON {player_id: roster_id}
    drops TEXT,               -- JSON {player_id: roster_id}
    draft_picks TEXT,         -- JSON array (para trades)
    created_at TIMESTAMP
);

-- Matchups semanais
CREATE TABLE matchups (
    league_id TEXT,
    week INTEGER,
    matchup_id INTEGER,
    roster_id INTEGER,
    points REAL,
    starters TEXT,            -- JSON array
    starters_points TEXT,     -- JSON array
    PRIMARY KEY (league_id, week, roster_id)
);
```

---

## Arquitetura de Dados

### Sleeper API — Endpoints Utilizados

| Endpoint | Retorno | Usado em |
|---|---|---|
| `GET /v1/user/{username}` | user_id, avatar, display_name | Setup inicial |
| `GET /v1/user/{user_id}/leagues/nfl/{season}` | Lista de ligas do usuário | Seleção de liga |
| `GET /v1/league/{league_id}` | Settings, scoring, roster_positions | Todos os pilares |
| `GET /v1/league/{league_id}/rosters` | Rosters com player_ids, starters, taxi, reserve | Roster Intelligence, Matchup |
| `GET /v1/league/{league_id}/users` | Display names, avatars, team names | Todos os pilares |
| `GET /v1/league/{league_id}/matchups/{week}` | Matchups da semana com pontuações | Matchup & Lineup |
| `GET /v1/league/{league_id}/transactions/{week}` | Trades, waivers, free agent adds | Roster Intelligence |
| `GET /v1/league/{league_id}/traded_picks` | Draft picks trocadas | Draft, Trade Finder |
| `GET /v1/draft/{draft_id}` | Metadata do draft (tipo, rounds, ordem, status) | Draft Companion |
| `GET /v1/draft/{draft_id}/picks` | Picks realizados com metadata do jogador | Draft Companion |
| `GET /v1/players/nfl` | Base completa de jogadores (~10k registros, cachear) | Mapeamento de IDs |

### FantasyPros — Scraping Pipeline

Dados obtidos via scripts Python locais (`/scrapers/fantasypros.py`). Cada execução gera JSON padronizado em `/data/rankings/` e insere no SQLite.

### Matriz de Rankings por Formato

O FantasyPros publica rankings separados por combinação de formato. O sistema detecta o formato de cada liga automaticamente (via `scoring_settings` e `roster_positions` do Sleeper) e puxa o ranking correto.

| Eixo | Variações | Como detectar no Sleeper |
|---|---|---|
| Tipo de liga | Dynasty / Redraft | `settings.type` (0=redraft, 2=dynasty) |
| Scoring | PPR / Half-PPR / Standard | `scoring_settings.rec` (1.0 / 0.5 / 0.0) |
| QB format | Superflex / 1QB | `SUPER_FLEX` in `roster_positions` |
| TE premium | TEP / Padrão | `scoring_settings.bonus_rec_te` > 0 |
| Extras | K, DEF | `K` ou `DEF` in `roster_positions` |

**Combinações de rankings que o scraper precisa cobrir:**

| Ranking type | Variações necessárias | URL FantasyPros (pattern) |
|---|---|---|
| Dynasty Overall | SF, 1QB | `/nfl/rankings/dynasty-overall.php?scoring=HALF&type=OP` |
| Dynasty Rookie | SF, 1QB | `/nfl/rankings/rookies.php?type=OP` |
| Redraft Overall | SF, 1QB | `/nfl/rankings/half-point-ppr-superflex-cheatsheets.php` |
| Weekly (by pos) | PPR, Half, Standard | `/nfl/rankings/half-point-ppr-qb.php?week=5` |
| Rest-of-Season | PPR, Half, Standard | `/nfl/rankings/ros-overall.php?scoring=HALF` |

O scraper recebe como argumento o formato desejado e resolve a URL correta internamente.

```bash
python scrapers/fantasypros.py --type dynasty --format sf_half_ppr
python scrapers/fantasypros.py --type weekly --format half_ppr --week 5
python scrapers/fantasypros.py --type rookie --format sf
```

| Script | Frequência sugerida | Usado em |
|---|---|---|
| `fantasypros.py --type rookie` | Pré-draft, semanal | Draft Companion |
| `fantasypros.py --type dynasty` | Semanal | Trade Finder, Roster Analysis |
| `fantasypros.py --type weekly` | Terça e sexta | Start/Sit, Lineup |
| `fantasypros.py --type ros` | Semanal | Waiver, Trade valuations |
| `fantasypros.py --type redraft` | Pré-draft (redraft) | Draft Companion (redraft) |

### Rankings no SQLite

```sql
CREATE TABLE rankings (
    player_name TEXT,
    player_id TEXT,            -- mapeado via fuzzy match com tabela players
    source TEXT DEFAULT 'fantasypros',
    ranking_type TEXT,         -- 'dynasty', 'redraft', 'weekly', 'ros', 'rookie'
    format TEXT,               -- 'sf_ppr', 'sf_half', '1qb_ppr', '1qb_half', '1qb_std'
    week INTEGER,              -- NULL exceto para weekly rankings
    rank INTEGER,
    position_rank TEXT,        -- 'WR12', 'QB3'
    value INTEGER,             -- valor normalizado (0-10000) para trade calc
    avg_adp REAL,
    best INTEGER,
    worst INTEGER,
    fetched_at TIMESTAMP,
    PRIMARY KEY (player_name, ranking_type, format, week, fetched_at)
);
```

**Formato de saída JSON (intermediário antes do SQLite):**

```json
{
  "source": "fantasypros",
  "type": "dynasty",
  "format": "sf_half_ppr",
  "week": null,
  "fetched_at": "2026-07-27T10:00:00Z",
  "players": [
    {
      "rank": 1,
      "name": "Ja'Marr Chase",
      "team": "CIN",
      "pos": "WR",
      "age": 26,
      "value": 9500,
      "best": 1,
      "worst": 3,
      "avg": 1.2,
      "std_dev": 0.4
    }
  ]
}
```

**Automação:** `make update-rankings` detecta quais formatos o usuário precisa (baseado nas ligas ativas no SQLite) e roda apenas os scrapers relevantes. Weekly rankings agendados via cron para terça 6h e sexta 6h.

**Resiliência:** Se o FantasyPros mudar a estrutura da página, o script falha silenciosamente e mantém o último JSON válido. Log de erros em `/data/rankings/errors.log`.

### Mapeamento Automático de Formato

Quando uma liga é sincronizada do Sleeper, o sistema classifica automaticamente:

```python
def classify_league(league_data):
    settings = league_data["settings"]
    scoring = league_data["scoring_settings"]
    positions = league_data["roster_positions"]

    return {
        "league_type": {0: "redraft", 1: "keeper", 2: "dynasty"}[settings["type"]],
        "scoring_type": {1.0: "ppr", 0.5: "half_ppr", 0.0: "standard"}.get(scoring.get("rec", 0), "custom"),
        "is_superflex": "SUPER_FLEX" in positions,
        "is_tep": scoring.get("bonus_rec_te", 0) > 0,
        "has_kicker": "K" in positions,
        "has_dst": "DEF" in positions,
        "ranking_format": _derive_ranking_format(scoring, positions)
    }

def _derive_ranking_format(scoring, positions):
    sf = "sf" if "SUPER_FLEX" in positions else "1qb"
    sc = {1.0: "ppr", 0.5: "half", 0.0: "std"}.get(scoring.get("rec", 0), "half")
    return f"{sf}_{sc}"
```

Isso permite que ao adicionar uma liga nova, o sistema já saiba qual ranking puxar sem configuração manual.

---

## Pilar 1 — Draft Companion

### Propósito

Painel auxiliar para usar durante drafts no Sleeper. Não substitui o draft room do Sleeper — complementa com rankings, tracking de targets e visão de necessidades.

Funciona para qualquer tipo de draft: rookie (dynasty), startup (dynasty), ou snake (redraft). O sistema detecta o tipo automaticamente via metadata do draft no Sleeper e carrega os rankings correspondentes.

### Funcionalidades

**Sync com Sleeper**
- Conecta via Draft ID
- Polling de picks a cada 5–10 segundos
- Detecta status do draft (pre_draft, drafting, complete)

**Rankings Board**
- Lista de jogadores rankeados por FantasyPros ECR
- Filtro por posição (ALL / QB / RB / WR / TE)
- Busca por nome
- Jogadores draftados removidos automaticamente da lista (ou marcados com strikethrough)
- Colunas: Rank, Nome, Pos, Time NFL, ADP, Best, Worst

**Player Targeting**
- Marcar jogadores como Target (estrela) ou Avoid (X)
- Filtro rápido para ver apenas targets
- Targets persistem entre sessões via storage

**Draft Board**
- Grid visual: linhas = rounds, colunas = times
- Cells color-coded por posição do jogador draftado
- Indicador de "on the clock"
- Picks trocadas refletidas com owner correto

**Team Viewer**
- Ver roster de qualquer time conforme draft avança
- Contagem de posições draftadas por time
- Highlight do seu time

---

## Pilar 2 — Roster Intelligence

### Propósito

Análise contínua do roster ao longo da temporada. Responde "o que meu time precisa?" e oferece caminhos para melhorar via trades e waivers.

Aplica-se a dynasty e redraft, mas com comportamento diferente conforme o tipo de liga.

### 2A — Roster Analysis

**Visão do Roster**
- Roster completo organizado por posição (starters, bench, taxi, IR)
- Valor de cada jogador usando o ranking correto pro formato da liga (dynasty value ou redraft value)
- Positional strength score (soma de valores por posição vs média da liga)
- `[dynasty]` Idade e taxi elegibility
- `[dynasty]` Age Curve — distribuição de idade, classificação Contender / Retooling / Rebuilder
- `[dynasty]` Projeção de janela competitiva
- `[redraft]` Bye week heatmap

**Depth Chart**
- Starters vs backups por posição
- Gap analysis: posições onde a queda de starter pra backup é mais acentuada
- Bye week conflicts
- `[sf]` QB depth é crítico — destacar se só tem 1 QB rosterable
- `[tep]` TE depth valorizado acima do normal

### 2B — Trade Finder

**Trade Value Engine**
- Atribuir valor a cada jogador usando rankings do formato correto da liga
- `[dynasty]` Picks valorizados com base em round e ano (1st 2026 > 1st 2027 > 2nd 2026)
- `[redraft]` Picks de draft não existem — trades são apenas jogadores
- `[sf]` QBs com multiplicador de valor
- `[tep]` TEs com multiplicador de valor

**Sugestão de Trade Partners**
- Para cada necessidade do meu time, encontrar owners com excesso nessa posição
- Cruzar: "eu tenho excesso de WR, Time X tem excesso de RB e precisa de WR" → match
- Mostrar sugestões de pacotes (jogador + pick por jogador)

**Trade Calculator**
- Input manual: lado A vs lado B
- Mostra diferença de valor e veredicto (fair / lopsided)
- Sugere peças para equilibrar
- Usa valores do formato da liga ativa

**Trade History**
- Histórico de trades da liga (via transactions endpoint)
- Analisar tendências de cada owner (quem vende barato, quem paga premium)

### 2C — Waivers & Free Agents

**Waiver Wire**
- Lista de free agents ordenada por FantasyPros ROS ranking
- Filtro por posição
- Highlight de jogadores com ownership% crescente (se dado disponível)

**FAAB Management**
- Budget restante por time
- Histórico de bids (quanto foi gasto em quem)
- Sugestão de bid % baseada em valor do jogador vs budget restante

**Add/Drop Recommendations**
- Comparar piores jogadores do meu bench com melhores free agents
- Sugerir swaps com justificativa (valor, bye week, handcuff)

---

## Pilar 3 — Matchup & Lineup

### Propósito

Gestão semanal durante a temporada regular. Responde "quem eu escalo?" e "como estou performando?"

### 3A — Start/Sit

**Lineup Optimizer**
- Puxar weekly rankings do FantasyPros
- Cruzar com roster do Sleeper
- Sugerir melhor lineup considerando:
  - Projeções de pontos
  - Formato da liga (SF, FLEX, TEP)
  - Matchup difficulty
- Marcar conflitos (jogador no IR, bye week, OUT/Doubtful)

**Decisões de Lineup**
- Para cada posição com dúvida, mostrar comparação head-to-head
- Argumentos a favor e contra cada opção
- Consenso dos experts (% de start rate)

### 3B — Matchup Center

**Matchup da Semana**
- Projeção de pontuação do meu time vs oponente
- Breakdown por posição: onde tenho vantagem e onde estou em desvantagem
- Live score tracking durante os jogos (polling do matchups endpoint)

**Win Probability**
- Baseado em projeções, estimar % de vitória
- Atualizar conforme jogos acontecem

### 3C — Season Dashboard

**Standings**
- Record de todos os times
- Points For / Points Against
- Posição no playoff race

**Power Rankings**
- Ranking semanal baseado em roster strength (não apenas W/L)
- Histórico de evolução ao longo da season

**Schedule**
- Próximos matchups com difficulty rating
- Semanas críticas (bye hell, playoffs)

---

## Features Transversais (Cross-Liga)

Funcionalidades que operam sobre todas as ligas do usuário simultaneamente.

**Player Lookup**
- Buscar jogador por nome
- Ver em quais ligas ele está rostereado, por qual time, e em qual slot (starter/bench/taxi/IR)
- Ver em quais ligas ele está disponível como free agent
- Mostrar ranking/valor dynasty ao lado para contexto

**Portfolio View**
- Visão consolidada de todos os jogadores que o usuário possui em qualquer liga
- Exposição total por jogador (em quantas ligas você tem o mesmo cara)
- Exposição por posição e por time NFL (risco de bye week concentrado, risco de lesão)

---

## Escopo de MVP vs Futuro

### MVP (construir primeiro)

| Feature | Pilar | Justificativa |
|---|---|---|
| Draft Companion (sync + rankings + board) | Draft | Necessidade imediata com draft se aproximando |
| Roster Viewer com valores | Roster Intelligence | Base para tudo que vem depois |
| Trade Calculator | Roster Intelligence | Uso constante em dynasty |
| Start/Sit semanal | Matchup & Lineup | Maior frequência de uso durante temporada |

### Fase 2

| Feature | Pilar |
|---|---|
| Trade Finder (sugestão automática de partners) | Roster Intelligence |
| Waiver recommendations | Roster Intelligence |
| Matchup projections | Matchup & Lineup |
| Season dashboard / standings | Matchup & Lineup |

### Fase 3

| Feature | Pilar |
|---|---|
| FAAB bidding strategy | Roster Intelligence |
| Owner tendencies / trade history | Roster Intelligence |
| Win probability live | Matchup & Lineup |
| Power rankings | Matchup & Lineup |
| Age curve / competitive window | Roster Intelligence |

---

## Convenções

- **IDs de jogadores**: Sleeper usa IDs numéricos como strings ("4034", "6904"). Toda referência a jogador passa por mapeamento via `/v1/players/nfl`.
- **Posições**: QB, RB, WR, TE, K, DEF. FLEX = RB/WR/TE. SUPER_FLEX = QB/RB/WR/TE.
- **Scoring reference**: Sempre respeitar o `scoring_settings` da liga específica. Não assumir half-PPR — ler do endpoint.
- **Multi-liga**: Cada liga tem seu contexto isolado. Rankings FantasyPros são compartilhados entre ligas do mesmo formato.

---

## Referências

- Sleeper API Docs: https://docs.sleeper.com
- FantasyPros Rankings: https://www.fantasypros.com/nfl/rankings/dynasty-overall.php
- FantasyPros Rookie Rankings: https://www.fantasypros.com/nfl/rankings/rookies.php
- FantasyCalc (referência de UX): https://fantasycalc.com
- Draft Wizard (referência de UI draft): https://draftwizard.fantasypros.com
