# Sleeper Fantasy Manager

Plataforma pessoal de gestão de ligas de fantasy football integrada ao [Sleeper](https://sleeper.com), com rankings do [FantasyPros](https://www.fantasypros.com), trade values do [FantasyCalc](https://fantasycalc.com) e rankings RSP.

## Requisitos

- Python 3.11+

## Setup

```bash
git clone https://github.com/pedrashow/sleeper-fantasy-manager.git
cd sleeper-fantasy-manager
pip install -r requirements.txt
python -c "from core.db import init_db; init_db()"
```

## Rodar

```bash
uvicorn web.server:app --reload --port 8000
```

Abrir `http://localhost:8000`. A Health page (`/health`) tem botões pra importar todas as fontes de dados.

## Import via CLI

```bash
python -m scrapers.sync_sleeper pedrashow
python -m scrapers.fantasypros --all
python -m scrapers.fantasycalc --all
python import_longbuild.py arquivo.xlsx --sheet all --db data/fantasy.db
```

## Estrutura

```
sleeper-fantasy-manager/
├── web/                  # FastAPI + HTMX (frontend)
│   ├── server.py         # entry point
│   ├── routes/           # handlers HTTP
│   ├── templates/        # Jinja2
│   └── static/           # CSS + htmx.min.js
├── core/                 # lógica de negócio e acesso a dados
│   ├── config.py         # constantes
│   ├── db.py             # schema SQLite, migrações
│   ├── formats.py        # mapeamento de formatos de ranking
│   ├── sleeper.py        # wrapper API Sleeper com cache TTL
│   ├── league_repo.py    # queries de ligas e rosters
│   ├── player_repo.py    # busca e detalhe de jogadores
│   ├── draft_repo.py     # lógica do draft assistant
│   └── waiver_repo.py    # lógica de waivers
├── scrapers/             # importação de dados
│   ├── fantasypros.py    # rankings FantasyPros
│   ├── fantasycalc.py    # trade values FantasyCalc
│   ├── rsp.py            # rankings RSP (Excel)
│   └── sync_sleeper.py   # sync ligas/rosters/jogadores
└── data/
    └── fantasy.db        # SQLite (gitignored)
```
