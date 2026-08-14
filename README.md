# Sleeper Fantasy Manager

Plataforma pessoal de gestão de ligas de fantasy football integrada ao [Sleeper](https://sleeper.com) e alimentada por rankings do [FantasyPros](https://www.fantasypros.com).

## Requisitos

- Python 3.11+
- pip

## Setup

```powershell
git clone https://github.com/pedrashow/sleeper-fantasy-manager.git
cd sleeper-fantasy-manager
pip install -r requirements.txt
```

## Uso

### Sync com Sleeper

```powershell
python manage.py sync pedrashow
```

### Rankings FantasyPros

```powershell
python manage.py rankings --type redraft --format half
python manage.py rankings --type redraft --format ppr
python manage.py rankings --type dynasty --format sf
python manage.py rankings --all
```

### Tudo de uma vez (Sync + Rankings)

```powershell
python manage.py update pedrashow
```

### Limpar banco e recomeçar

```powershell
python manage.py clean
```

### Streamlit App (em construção)

```powershell
python manage.py app
```

## Estrutura

```
sleeper-fantasy-manager/
├── app/
│   ├── pages/
│   └── Home.py
├── core/
│   ├── db.py               ← SQLite schema e helpers
│   └── sleeper.py          ← Client da API do Sleeper
├── scrapers/
│   ├── fantasypros.py      ← Scraper de rankings (overall + por posição)
│   └── sync_sleeper.py     ← Sync Sleeper → SQLite
├── data/
│   ├── fantasy.db          ← SQLite (gitignored)
│   └── rankings/           ← JSONs cacheados (gitignored)
├── manage.py               ← CLI principal
├── requirements.txt
└── PROJECT.md              ← Documentação completa do projeto
```

## Rankings

O scraper puxa rankings overall (tier geral) e por posição (tier por posição) automaticamente.

Dados capturados por jogador: rank, tier geral, tier posicional, ADP, best, worst, bye week, ownership %, ECR delta.

## Formatos suportados

| Eixo | Variações |
|---|---|
| Tipo | Dynasty / Keeper / Redraft |
| Scoring | PPR / Half-PPR / Standard |
| QB | Superflex / 1QB |
| TE Premium | TEP / Padrão |
| Extras | K, DST |
