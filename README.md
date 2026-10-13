# PalpiteFC

Chance estatística dos jogos do Brasileirão Série A. Não é casa de aposta: não recebe valor, não recomenda aposta e não garante acerto.

## O que o site mostra

- **Rodada**: a próxima rodada com a data prevista e os jogos atrasados, a última rodada com a chance do modelo e a da odd sem margem lado a lado.
- **Tabela**: a classificação, a chance de título, G4, 5º lugar, Sul-Americana e rebaixamento no fim do campeonato, os pontos esperados, os pontos necessários para cada objetivo e os jogos que mais mexem na tabela, na próxima rodada e no resto do campeonato.
- **Times**: posição de hoje, chance de terminar em cada posição e os confrontos que faltam, em ordem de data.
- **Simular**: qualquer confronto, com a grade de placares.
- **A conta**: a conferência da temporada (RPS, Brier, log loss, calibração e o dinheiro que a regra de "vantagem" teria perdido) e a conferência da tabela simulada em temporadas passadas.

## O modelo

Dixon-Coles: gols de cada time, mando de campo, correção para placares baixos e mais peso para o jogo recente. Vitória, empate, derrota, ambos marcam, mais de 1,5/2,5/3,5 gols e os placares saem da mesma tabela, para as chances não se contradizerem.

- O peso de um jogo cai pela metade a cada 347 dias (`xi = 0,002` por dia).
- Uma regularização L2 (`l2 = 10`) puxa ataque e defesa para um centro e segura o time com poucos jogos na base. O centro é a média da liga, menos para o time que subiu da Série B: ele é puxado para 0,1 abaixo da média no ataque e 0,1 acima na defesa.
- Os três números saem de `python -m palpitefc.calibrar`, que escolhe pelo menor RPS em 2024 e 2025, jogo a jogo e sem olhar o resultado à frente. A temporada 2026 fica de fora da escolha e serve de prova: o centro do promovido levou o RPS de 0,2047 para 0,2042.
- O ajuste usa o gradiente analítico da verossimilhança. Ficou cerca de 12 vezes mais rápido que a diferença finita: a temporada inteira é refeita em segundos.
- A margem da casa sai da odd pelo método de Shin, o padrão do penaltyblog e do pacote `implied`.
- Testei aumentar a chance de empate, como fazia o FiveThirtyEight, e não ajudou: o modelo já acerta a frequência de empates nas temporadas de escolha.

## A tabela simulada

A tabela final vem de 20 mil simulações dos jogos que faltam, com o desempate da CBF (pontos, vitórias, saldo, gols marcados) e as vagas de 2026 (G4 na Libertadores, 5º na fase prévia, 6º a 11º na Sul-Americana, Z4 cai).

A força de cada time não é conhecida com exatidão. A covariância dos parâmetros é H⁻¹ (J + P) H⁻¹: J é a parte sanduíche, que respeita o peso de cada jogo, e P é a curvatura da regularização, lida como uma priori. Sem P, o time com poucos jogos, muito puxado para o centro, sairia com incerteza quase zero; com P, o desvio do ataque do Mirassol depois de 3 rodadas de 2025 é 0,17, e o do Flamengo, 0,08. Sem regularização, o intervalo de 95% acertou o valor real em 93% das vezes numa simulação de conferência. A tabela sorteia 200 versões do modelo dessa covariância, cada uma com 100 temporadas. Sem isso, a força estimada vira certeza e a tabela fica confiante demais.

`python -m palpitefc.conferir_tabela` confere a simulação em temporadas que já acabaram: corta cada uma depois de 5, 10, 19 e 28 rodadas, ajusta o modelo só com o que havia até ali e compara a chance de cada posição com a classificação final.

| Prova 2020–2025 (menor é melhor) | RPS da posição | Brier título | Brier G4 | Brier Z4 |
| --- | --- | --- | --- | --- |
| Com incerteza (escala 1,5) | 0,0993 | 0,036 | 0,087 | 0,111 |
| Sem incerteza | 0,1012 | 0,036 | 0,087 | 0,116 |
| Tabela de hoje fica como está | 0,1601 | 0,071 | 0,117 | 0,154 |

A escala 1,5 foi escolhida só em 2013–2019, e na prova melhora as quatro notas (as de título e G4 por pouco). Uma ressalva: xi, l2 e o centro do promovido foram escolhidos em 2024–2025, que estão dentro desta prova.

A curva de pontos necessários junta todos os times de todas as simulações: de quem terminou com tantos pontos, quantos foram campeões, ficaram no G4 ou escaparam do Z4.

## A conferência de 2026

Está em `data/retrospectiva.json`. Cada jogo foi calculado só com resultados anteriores.

| Previsão (297 jogos até 13/10) | RPS | Brier | Log loss |
| --- | --- | --- | --- |
| Odd de fechamento sem margem | 0,197 | 0,597 | 0,997 |
| PalpiteFC | 0,204 | 0,614 | 1,022 |
| Média da liga | 0,218 | 0,639 | 1,059 |

Menor é melhor. A odd foi melhor que o modelo por 0,0072 de RPS, com intervalo de 95% entre 0,001 e 0,014 (bootstrap pareado). O modelo bate a média da liga com folga, e a regra de "vantagem sobre a odd" perdeu dinheiro. Por isso o site publica a chance e não marca palpite de aposta.

Para comparar: no Brasileirão 2021, um estudo da FGV mediu RPS de 0,205 para a casa de aposta, 0,205 para o FiveThirtyEight, 0,210 para o Chance de Gol e 0,218 para o modelo da UFMG ([pôster](https://eventos.fgv.br/sites/eventos.fgv.br/files/arquivos/u1252/poster_flavio_fontanella.pdf)). São temporadas diferentes, então a comparação é só de ordem de grandeza.

## Rodar

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .
uvicorn palpitefc.server:app --host 0.0.0.0 --port 8080
```

Precisa de Python 3.12 ou mais novo (o scipy 1.18 exige).

## Atualizar os dados

Os resultados, as odds e os próximos jogos vêm do [football-data.co.uk](https://www.football-data.co.uk/). O calendário da temporada, com rodada e data prevista, vem do [openfootball](https://github.com/openfootball/football.json) (domínio público). Ele atrasa algumas semanas, então a data é só a prevista; quando o football-data lista o jogo, a data dele vale mais.

```bash
python -m palpitefc.atualizar
```

O comando baixa os três arquivos, confere se o de resultados não perdeu jogos e refaz só a parte nova da conferência. Para recalcular tudo do zero, use `python -m palpitefc.retrospectiva --do-zero`. Depois de mudar o modelo, rode também `python -m palpitefc.calibrar` e `python -m palpitefc.conferir_tabela`.

O workflow `Atualizar dados` roda a atualização todo dia às 07h15 de Brasília e faz commit só quando há dado novo. O deploy do Railway parte desse commit.

## Deploy

Repositório próprio, separado do site de loterias. No Railway, a raiz do serviço é este repositório. Não aponte o serviço do Powerball para cá. O `railway.toml` define o comando de início e o healthcheck em `/api/saude`; o `.python-version` fixa o Python 3.12.

## Referências

- Dixon e Coles (1997), *Modelling association football scores and inefficiencies in the football betting market*.
- Constantinou e Fenton (2012), *Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models*.
- Shin (1993), *Measuring the incidence of insider trading in a market for state-contingent claims*; Štrumbelj (2014), *On determining probability forecasts from betting odds*.
- Projetos parecidos: [penaltyblog](https://github.com/martineastwood/penaltyblog), [goalmodel](https://github.com/opisthokonta/goalmodel), [Probabilidades no Futebol (UFMG)](https://www.mat.ufmg.br/futebol/serie-a/), [ValorFinal](https://valorfinal.com.br/brasileirao/metodologia), [FiveThirtyEight](https://web.archive.org/web/2023id_/https://fivethirtyeight.com/methodology/how-our-club-soccer-predictions-work/).
