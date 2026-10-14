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

| Prova 2020–2023 (menor é melhor) | RPS da posição | Brier título | Brier G4 | Brier Z4 |
| --- | --- | --- | --- | --- |
| Com incerteza (escala 1,5) | 0,0935 | 0,0355 | 0,0973 | 0,1025 |
| Sem incerteza | 0,0940 | 0,0355 | 0,0974 | 0,1046 |
| Tabela de hoje fica como está | 0,1526 | 0,0688 | 0,1313 | 0,1313 |

A escala 1,5 foi escolhida em 2013–2019. Na prova, melhora o RPS da posição e o Brier do Z4, e empata no título e no G4. A prova para em 2023 de propósito: xi, l2 e o centro do promovido foram escolhidos em 2024–2025, e uma prova que já viu a resposta não prova nada.

A curva de pontos necessários junta todos os times de todas as simulações: de quem terminou com tantos pontos, quantos foram campeões, ficaram no G4 ou escaparam do Z4.

## A conferência de 2026

Está em `data/retrospectiva.json`. Cada jogo foi calculado só com resultados anteriores.

| Previsão (299 jogos até 12/10) | RPS | Brier | Log loss |
| --- | --- | --- | --- |
| Odd de fechamento sem margem | 0,197 | 0,597 | 0,996 |
| PalpiteFC | 0,204 | 0,613 | 1,020 |
| Média da liga | 0,217 | 0,637 | 1,057 |

Menor é melhor. A odd foi melhor que o modelo por 0,0070 de RPS, com intervalo de 95% entre 0,001 e 0,013 (bootstrap pareado). Time que subiu sem histórico na base entra com o centro do promovido desde o primeiro jogo, então nenhum jogo da temporada fica de fora. O modelo bate a média da liga com folga, e a regra de "vantagem sobre a odd" perdeu dinheiro. Por isso o site publica a chance e não marca palpite de aposta.

Para comparar: no Brasileirão 2021, um estudo da FGV mediu RPS de 0,205 para a casa de aposta, 0,205 para o FiveThirtyEight, 0,210 para o Chance de Gol e 0,218 para o modelo da UFMG ([pôster](https://eventos.fgv.br/sites/eventos.fgv.br/files/arquivos/u1252/poster_flavio_fontanella.pdf)). São temporadas diferentes, então a comparação é só de ordem de grandeza.

## Rodar

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .
uvicorn palpitefc.server:app --host 0.0.0.0 --port 8080
```

Precisa de Python 3.12 ou mais novo (o scipy 1.18 exige).

## Atualizar os dados

Os resultados, as odds e os próximos jogos vêm do [football-data.co.uk](https://www.football-data.co.uk/), que publica a hora do Reino Unido; o site converte tudo para a hora de Brasília na leitura.

O calendário da temporada, com rodada e data, vem de uma de duas fontes:

- [football-data.org](https://www.football-data.org/), se houver a variável `FOOTBALL_DATA_ORG_TOKEN`. É oficial e traz a hora assim que a CBF confirma. A chave é gratuita: crie a conta em football-data.org/client/register e cadastre a chave no GitHub em Settings → Secrets and variables → Actions, com o nome `FOOTBALL_DATA_ORG_TOKEN`.
- [openfootball](https://github.com/openfootball/football.json) (domínio público), sem chave nenhuma. Atrasa algumas semanas e põe na rodada inteira a data do primeiro dia, por isso o site mostra "a partir de".

Se a fonte com chave falhar, o openfootball entra no lugar. Em qualquer caso, a data e a hora do football-data.co.uk valem mais quando ele lista o jogo, às terças e sextas.

```bash
python -m palpitefc.atualizar
```

O comando baixa os três arquivos, confere se o de resultados não perdeu jogos e refaz só a parte nova da conferência. Cada campo do calendário é validado antes de chegar à página. Para recalcular tudo do zero, use `python -m palpitefc.retrospectiva --do-zero`. Depois de mudar o modelo, rode também `python -m palpitefc.calibrar` e `python -m palpitefc.conferir_tabela`.

O workflow `Atualizar dados` roda a atualização todo dia às 07h15 e às 17h30 de Brasília e faz commit só quando há dado novo. A rodada da tarde pega no mesmo dia a lista de próximos jogos que o football-data publica às terças e sextas. O deploy do Railway parte desse commit.

## Placar ao vivo

Com a variável `BSD_TOKEN` no Railway (chave gratuita da [Bzzoiro Sports Data](https://sports.bzzoiro.com/pricing/)), o servidor consulta os jogos em andamento da Série A. Sem o token, nada disso roda e o site fica como antes.

- A cada 20 segundos na janela de cada jogo (de 10 minutos antes do início até 2h30 depois) e enquanto a fonte mostrar um jogo em andamento, mesmo depois da janela (início atrasado, paralisação), com teto de 4 horas.
- A cada 2 minutos no dia de jogo sem hora confirmada (e nos 3 dias seguintes, porque o openfootball põe a rodada inteira no primeiro dia), e a cada 10 minutos no resto do dia, das 11h à meia-noite, para achar jogo remarcado. De madrugada, nada. Com o calendário que falta de 2026, o dia mais cheio dá cerca de 1.400 consultas, longe da cota grátis de 7.500.
- Ao ligar, uma consulta busca os jogos encerrados dos últimos 4 dias: o placar visto ao vivo fica só na memória, e cada deploy o apagaria antes de o arquivo de resultados trazê-lo.

Na página:

- A Rodada mostra placar, minuto e situação de cada jogo, e se atualiza sozinha (a cada 30 segundos perto de jogo, a cada 90 no resto do tempo). O jogo que começou sai da lista de próximos jogos.
- Sem notícia da fonte por 3 minutos, o jogo deixa de aparecer como "ao vivo" e passa a "sem atualização desde HH:MM".
- A cada gol, a tabela do fim do campeonato é refeita como se os jogos em andamento terminassem assim ("Se terminar assim"), com o resto do campeonato simulado de novo.
- O jogo em andamento não ganha chance de vitória: é o número usado para apostar ao vivo, e o site não mostra.
- O leitor de tela ouve só as frases curtas ("Gol: …", "Fim de jogo: …"), não o bloco inteiro a cada atualização.

`/api/saude` informa se o ao vivo está ativo, a última consulta, o último erro e os times sem id da Bzzoiro, sem o token. A licença da Bzzoiro permite mostrar os dados no próprio site, não repassá-los como feed: `/api/aovivo` existe só para as páginas do PalpiteFC.

## Virada de temporada

A temporada do site é a mais recente do `BRA.csv`: quando o primeiro jogo de 2027 entrar, o site muda sozinho, e o calendário passa a ser baixado para 2027. Time sem histórico na base entra com o centro do promovido. O que precisa de gente, em janeiro:

- conferir as vagas da CBF para o ano novo em `ZONAS` (`palpitefc/simulacao.py`);
- incluir os times novos em `NOMES` e `NOMES_OPENFOOTBALL` (`palpitefc/dados.py`); sem isso, o calendário é ignorado e o nome aparece como no CSV;
- incluir os ids da Bzzoiro dos times novos em `IDS_BZZOIRO` (`palpitefc/dados.py`); sem isso, o jogo deles não aparece ao vivo. `/api/saude` lista em `aoVivo.timesSemId` os que faltam;
- revisar o texto do termo de uso em `web/index.html`, que cita a temporada 2026.

## Deploy

Repositório próprio, separado do site de loterias. No Railway, a raiz do serviço é este repositório. Não aponte o serviço do Powerball para cá. O `railway.toml` define o comando de início e o healthcheck em `/api/saude`; o `.python-version` fixa o Python 3.12.

## Referências

- Dixon e Coles (1997), *Modelling association football scores and inefficiencies in the football betting market*.
- Constantinou e Fenton (2012), *Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models*.
- Shin (1993), *Measuring the incidence of insider trading in a market for state-contingent claims*; Štrumbelj (2014), *On determining probability forecasts from betting odds*.
- Projetos parecidos: [penaltyblog](https://github.com/martineastwood/penaltyblog), [goalmodel](https://github.com/opisthokonta/goalmodel), [Probabilidades no Futebol (UFMG)](https://www.mat.ufmg.br/futebol/serie-a/), [ValorFinal](https://valorfinal.com.br/brasileirao/metodologia), [FiveThirtyEight](https://web.archive.org/web/2023id_/https://fivethirtyeight.com/methodology/how-our-club-soccer-predictions-work/).
