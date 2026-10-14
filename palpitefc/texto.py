"""Texto curto de um jogo, montado só com os números do site.

Nada aqui vem de notícia, escalação ou opinião: cada frase sai da forma
recente, da tabela de placares do modelo, do confronto direto e da
simulação do campeonato. Por isso o texto não pode errar um fato que o
resto da página não mostre, e não usa palavra de aposta.
"""

from __future__ import annotations

import math

# Efeito menor que isso (5 pontos percentuais) não vira frase: seria ruído.
EFEITO_MINIMO = 0.05
ZONAS_EM_TEXTO = {"titulo": "título", "libertadores": "G4", "rebaixamento": "cair"}


def _pct(valor: float) -> str:
    """Igual ao pct() da página: nunca 0% nem 100%, que a simulação não garante."""
    numero = valor * 100
    if numero < 0.5:
        return "menos de 1%"
    if numero >= 99.5:
        return "mais de 99%"
    # Meio para cima, como o toFixed do navegador (o format do Python arredonda para o par).
    return f"{math.floor(numero + 0.5)}%"


NENHUM = {"vitória": "nenhuma vitória", "empate": "nenhum empate", "jogo": "nenhum jogo"}


def _plural(quantos: int, singular: str, plural: str) -> str:
    if quantos == 0 and singular in NENHUM:
        return NENHUM[singular]
    return f"{quantos} {singular if quantos == 1 else plural}"


def _lista(itens: list[str]) -> str:
    if len(itens) < 2:
        return "".join(itens)
    return f"{', '.join(itens[:-1])} e {itens[-1]}"


def contagem_da_forma(letras: list[str]) -> str:
    partes = []
    for letra, singular, plural in (("V", "vitória", "vitórias"), ("E", "empate", "empates"), ("D", "derrota", "derrotas")):
        quantos = letras.count(letra)
        if quantos:
            partes.append(_plural(quantos, singular, plural))
    return _lista(partes)


def frase_da_forma(nome: str, forma: list[dict]) -> str | None:
    if not forma:
        return None
    letras = [jogo["resultado"] for jogo in forma]
    periodo = "no último jogo" if len(letras) == 1 else f"nos últimos {len(letras)} jogos"
    return f"{nome}: {contagem_da_forma(letras)} {periodo} na Série A."


def frase_da_chance(cartao: dict) -> str:
    chance = cartao["chance"]
    placar = cartao["placares"][0] if cartao.get("placares") else None
    texto = (
        f"Pela conta, {cartao['casaNome']} {_pct(chance['casa'])}, empate {_pct(chance['empate'])} "
        f"e {cartao['foraNome']} {_pct(chance['fora'])}."
    )
    if placar:
        texto += f" Placar mais provável: {placar['casa']}–{placar['fora']} ({_pct(placar['chance'])})."
    return texto


def frase_do_confronto(cartao: dict, confronto: dict) -> str:
    casa, fora = cartao["casa"], cartao["fora"]
    if not confronto["jogos"]:
        desde = confronto.get("inicioDaBase")
        return f"Primeiro encontro na Série A da base{f', que começa em {desde}' if desde else ''}."
    vitorias = confronto["vitorias"]
    # Sem artigo: "do Palmeiras", mas "da Chapecoense".
    def vitorias_de(nome: str, quantas: int) -> str:
        return f"{nome} sem vitória" if quantas == 0 else f"{nome} com {_plural(quantas, 'vitória', 'vitórias')}"

    partes = [
        vitorias_de(cartao["casaNome"], vitorias[casa]),
        vitorias_de(cartao["foraNome"], vitorias[fora]),
        _plural(confronto["empates"], "empate", "empates"),
    ]
    return f"Na Série A desde {confronto['desde']}: {_plural(confronto['jogos'], 'jogo', 'jogos')}, {_lista(partes)}."


def frases_do_impacto(impacto: dict | None) -> list[str]:
    if not impacto:
        return []
    frases = []
    for efeito in impacto.get("efeitos", []):
        if efeito["diferenca"] < EFEITO_MINIMO or efeito["zona"] not in ZONAS_EM_TEXTO:
            continue
        frases.append(
            f"{efeito['nome']}: chance de {ZONAS_EM_TEXTO[efeito['zona']]} de {_pct(efeito['sePerder'])} "
            f"se perder a {_pct(efeito['seVencer'])} se vencer."
        )
    return frases


def resumo_do_jogo(
    cartao: dict,
    forma_casa: list[dict],
    forma_fora: list[dict],
    confronto: dict,
    impacto: dict | None = None,
) -> list[str]:
    """Frases curtas, na ordem em que um torcedor perguntaria."""
    frases = [frase_da_forma(cartao["casaNome"], forma_casa), frase_da_forma(cartao["foraNome"], forma_fora)]
    frases.append(frase_da_chance(cartao))
    frases.append(frase_do_confronto(cartao, confronto))
    frases.extend(frases_do_impacto(impacto))
    return [frase for frase in frases if frase]
