# PalpiteFC

Chance estatística dos jogos do Brasileirão Série A. Não é casa de aposta: não recebe valor, não recomenda aposta e não garante acerto.

## O que o site mostra

- **Rodada**: a última rodada, com a chance do modelo e a da odd sem margem lado a lado, e os próximos jogos quando o football-data publica a lista.
- **Tabela**: a classificação, a chance de título, G4, 5º lugar, Sul-Americana e rebaixamento no fim do campeonato, os pontos esperados e os jogos que mais mexem na tabela.
- **Times**: posição de hoje, chance de terminar em cada posição e os confrontos que faltam.
- **Simular**: qualquer confronto, com a grade de placares.
- **A conta**: a conferência da temporada, com RPS, Brier, log loss, calibração e o dinheiro que a regra de "vantagem" teria perdido.

## O modelo

Dixon-Coles: gols de cada time, mando de campo, correção para placares baixos e mais peso para o jogo recente. Vitória, empate, derrota, ambos marcam, mais de 1,5/2,5/3,5 gols e os placares saem da mesma tabela, para as chances não se contradizerem.

- O peso de um jogo cai pela metade a cada 347 dias (`xi = 0,002` por dia).
- Uma regularização L2 (`l2 = 10`) puxa ataque e defesa para a média e segura o time recém-promovido, que chega com poucos jogos na base.
- Os dois números saem de `python -m palpitefc.calibrar`, que escolhe pelo menor RPS em 2024 e 2025, jogo a jogo e sem olhar o resultado à frente. A temporada 2026 fica de fora da escolha e serve de prova.
- O ajuste usa o gradiente analítico da verossimilhança. Ficou cerca de 12 vezes mais rápido que a diferença finita: a temporada inteira é refeita em segundos.
- A tabela final vem de 20 mil simulações dos jogos que faltam, com o desempate da CBF (pontos, vitórias, saldo, gols marcados).
- A margem da casa sai da odd pelo método de Shin, o padrão do penaltyblog e do pacote `implied`.

## A conferência de 2026

Está em `data/retrospectiva.json`. Cada jogo foi calculado só com resultados anteriores.

| Previsão (297 jogos até 13/10) | RPS | Brier | Log loss |
| --- | --- | --- | --- |
| Odd de fechamento sem margem | 0,197 | 0,597 | 0,997 |
| PalpiteFC | 0,205 | 0,615 | 1,023 |
| Média da liga | 0,218 | 0,639 | 1,059 |

Menor é melhor. A odd foi melhor que o modelo por 0,0077 de RPS, com intervalo de 95% entre 0,001 e 0,015 (bootstrap pareado). O modelo bate a média da liga com folga, e a regra de "vantagem sobre a odd" perdeu dinheiro. Por isso o site publica a chance e não marca palpite de aposta.

Para comparar: no Brasileirão 2021, um estudo da FGV mediu RPS de 0,205 para a casa de aposta, 0,205 para o FiveThirtyEight, 0,210 para o Chance de Gol e 0,218 para o modelo da UFMG ([pôster](https://eventos.fgv.br/sites/eventos.fgv.br/files/arquivos/u1252/poster_flavio_fontanella.pdf)). São temporadas diferentes, então a comparação é só de ordem de grandeza.

## Rodar

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .
uvicorn palpitefc.server:app --host 0.0.0.0 --port 8080
```

Precisa de Python 3.12 ou mais novo (o scipy 1.18 exige).

## Atualizar os dados

Os resultados, as odds e os próximos jogos vêm do [football-data.co.uk](https://www.football-data.co.uk/).

```bash
python -m palpitefc.atualizar
```

O comando baixa o `BRA.csv` e a lista de próximos jogos, confere se o arquivo novo não perdeu jogos e refaz só a parte nova da conferência. Para recalcular tudo do zero, use `python -m palpitefc.retrospectiva --do-zero`.

O workflow `Atualizar dados` roda isso todo dia às 07h15 de Brasília e faz commit só quando há dado novo. O deploy do Railway parte desse commit.

## Deploy

Repositório próprio, separado do site de loterias. No Railway, a raiz do serviço é este repositório. Não aponte o serviço do Powerball para cá. O `railway.toml` define o comando de início e o healthcheck em `/api/saude`; o `.python-version` fixa o Python 3.12.

## Referências

- Dixon e Coles (1997), *Modelling association football scores and inefficiencies in the football betting market*.
- Constantinou e Fenton (2012), *Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models*.
- Shin (1993), *Measuring the incidence of insider trading in a market for state-contingent claims*; Štrumbelj (2014), *On determining probability forecasts from betting odds*.
- Projetos parecidos: [penaltyblog](https://github.com/martineastwood/penaltyblog), [goalmodel](https://github.com/opisthokonta/goalmodel), [Probabilidades no Futebol (UFMG)](https://www.mat.ufmg.br/futebol/serie-a/), [ValorFinal](https://valorfinal.com.br/brasileirao/metodologia).
