import re
import unittest
from datetime import datetime, timedelta

from palpitefc.historico import confronto, forma
from palpitefc.texto import _pct, contagem_da_forma, frase_da_forma, frases_do_impacto, resumo_do_jogo


def jogo(dia, casa, fora, gols_casa, gols_fora, temporada="2026"):
    return {
        "temporada": temporada,
        "quando": datetime(2026, 1, 1) + timedelta(days=dia),
        "casa": casa,
        "fora": fora,
        "gols_casa": gols_casa,
        "gols_fora": gols_fora,
    }


JOGOS = [
    jogo(1, "A", "B", 2, 0, "2025"),
    jogo(2, "C", "A", 1, 1),
    jogo(3, "B", "A", 3, 1),
    jogo(4, "A", "C", 0, 0),
    jogo(5, "A", "B", 1, 0),
    jogo(6, "C", "A", 0, 2),
    jogo(7, "A", "B", None, None),
]


class TesteForma(unittest.TestCase):
    def test_ultimos_jogos_do_mais_recente_para_o_mais_antigo(self):
        linhas = forma(JOGOS, "A")
        self.assertEqual([linha["resultado"] for linha in linhas], ["V", "V", "E", "D", "E"])
        self.assertEqual(linhas[0]["mando"], "fora")
        self.assertEqual((linhas[0]["golsPro"], linhas[0]["golsContra"]), (2, 0))
        self.assertEqual(linhas[3]["adversario"], "B")

    def test_time_sem_jogos(self):
        self.assertEqual(forma(JOGOS, "Z"), [])

    def test_so_as_temporadas_pedidas(self):
        # O jogo de 2025 sai: quem volta depois de anos não mostra forma antiga.
        self.assertEqual(len(forma(JOGOS, "B", temporadas={"2026"})), 2)
        self.assertEqual(forma(JOGOS, "A", temporadas={"2027"}), [])


class TesteConfronto(unittest.TestCase):
    def test_conta_dos_dois_lados(self):
        dados = confronto(JOGOS, "A", "B")
        self.assertEqual(dados["jogos"], 3)
        self.assertEqual(dados["vitorias"], {"A": 2, "B": 1})
        self.assertEqual(dados["empates"], 0)
        self.assertEqual(dados["gols"], {"A": 4, "B": 3})
        self.assertEqual(dados["desde"], "2025")
        self.assertEqual(dados["ultimos"][0]["golsCasa"], 1)
        self.assertEqual(confronto(JOGOS, "B", "A")["vitorias"], {"B": 1, "A": 2})

    def test_sem_encontro(self):
        dados = confronto(JOGOS, "B", "C")
        self.assertEqual((dados["jogos"], dados["desde"], dados["inicioDaBase"]), (0, None, "2025"))


CARTAO = {
    "casa": "A",
    "fora": "B",
    "casaNome": "Alfa",
    "foraNome": "Chapecoense",
    "chance": {"casa": 0.452, "empate": 0.281, "fora": 0.267},
    "placares": [{"casa": 1, "fora": 1, "chance": 0.128}],
}


class TesteTexto(unittest.TestCase):
    def test_contagem_com_plural_e_sem_zeros(self):
        self.assertEqual(contagem_da_forma(["V", "V", "E", "D", "V"]), "3 vitórias, 1 empate e 1 derrota")
        self.assertEqual(contagem_da_forma(["E"]), "1 empate")

    def test_resumo_completo_sem_palavra_de_aposta(self):
        impacto = {
            "efeitos": [
                {"nome": "Alfa", "zona": "titulo", "sePerder": 0.10, "seVencer": 0.54, "diferenca": 0.44},
                {"nome": "Chapecoense", "zona": "rebaixamento", "sePerder": 0.99, "seVencer": 0.97, "diferenca": 0.02},
            ]
        }
        frases = resumo_do_jogo(CARTAO, forma(JOGOS, "A"), forma(JOGOS, "B"), confronto(JOGOS, "A", "B"), impacto)
        texto = " ".join(frases)
        self.assertIn("Alfa: 2 vitórias, 2 empates e 1 derrota nos últimos 5 jogos na Série A.", texto)
        self.assertIn("Pela conta, Alfa 45%, empate 28% e Chapecoense 27%.", texto)
        self.assertIn("Placar mais provável: 1–1 (13%).", texto)
        self.assertIn("Alfa com 2 vitórias, Chapecoense com 1 vitória e nenhum empate", texto)
        self.assertIn("Alfa: chance de título de 10% se perder a 54% se vencer.", texto)
        # Efeito de 2 pontos é ruído e não vira frase.
        self.assertNotIn("Chapecoense: chance de cair", texto)
        self.assertNotIn(" do Chapecoense", texto)
        self.assertIsNone(re.search(r"apost|odd|valor|lucro|green|banca", texto, re.IGNORECASE))

    def test_um_jogo_so(self):
        self.assertEqual(frase_da_forma("Remo", forma(JOGOS, "C")[:1]), "Remo: 1 derrota no último jogo na Série A.")

    def test_percentuais_como_na_pagina(self):
        self.assertEqual(_pct(0.0), "menos de 1%")
        self.assertEqual(_pct(0.004), "menos de 1%")
        self.assertEqual(_pct(1.0), "mais de 99%")
        self.assertEqual(_pct(0.996), "mais de 99%")
        self.assertEqual(_pct(0.125), "13%")
        self.assertEqual(_pct(0.445), "45%")

    def test_primeiro_encontro(self):
        frases = resumo_do_jogo({**CARTAO, "fora": "C"}, [], [], confronto(JOGOS, "B", "C"))
        self.assertIn("Primeiro encontro na Série A da base, que começa em 2025.", frases)

    def test_impacto_vazio(self):
        self.assertEqual(frases_do_impacto(None), [])


if __name__ == "__main__":
    unittest.main()
