# PalpiteFC

Chance estatística dos jogos do Brasileirão Série A. Não é casa de aposta: não recebe valor, não recomenda aposta e não garante acerto.

O cálculo é o Dixon-Coles (gols de cada time, mando de campo, jogos recentes com mais peso). Vitória, empate, derrota, ambos marcam, mais de 2,5 gols e os placares saem da mesma tabela, para as chances não se contradizerem.

A conferência de 2026 está em `data/retrospectiva.json`. Cada jogo foi calculado só com resultados anteriores. Nessa temporada a odd favorita acertou mais do que o modelo, e a regra de “vantagem sobre a odd” perdeu dinheiro. O site publica esses números e não marca palpite de aposta.

Os resultados e as odds vêm do [football-data.co.uk](https://www.football-data.co.uk/). Para atualizar:

```bash
curl -fsSL -o data/BRA.csv https://www.football-data.co.uk/new/BRA.csv
python -m palpitefc.retrospectiva
```

```bash
pip install -r requirements.txt
python -m unittest tests.test_modelo
uvicorn palpitefc.server:app --host 0.0.0.0 --port 8080
```

Repositório próprio, separado do site de loterias. No Railway, a raiz do serviço é este repositório. Não aponte o serviço do Powerball para cá.
