import unittest
from datetime import datetime, timedelta

from palpitefc.model import ajustar, mercados, tabela_de_placares
from palpitefc.palpite import avaliar


class TesteModelo(unittest.TestCase):
    def test_tabela_soma_um_e_corrige_placar_baixo(self):
        grade = tabela_de_placares(1.4, 1.1, -0.1)
        self.assertAlmostEqual(float(grade.sum()), 1.0, places=6)
        independente = tabela_de_placares(1.4, 1.1, 0.0)
        self.assertGreater(grade[0, 0], independente[0, 0])

    def test_mercados_fecham_o_resultado(self):
        grade = tabela_de_placares(1.5, 1.2, -0.05)
        chance = mercados(grade)
        self.assertAlmostEqual(chance["casa"] + chance["empate"] + chance["fora"], 1.0, places=6)
        self.assertGreater(chance["mais15"], chance["mais25"])
        self.assertGreater(chance["mais25"], chance["mais35"])

    def test_time_que_sempre_vence_em_casa_segue_favorito(self):
        forte, fraco = "Forte", "Fraco"
        jogos = []
        inicio = datetime(2026, 1, 1)
        for dia in range(40):
            quando = inicio + timedelta(days=dia)
            jogos.append(
                {
                    "casa": forte,
                    "fora": fraco,
                    "gols_casa": 2,
                    "gols_fora": 0,
                    "dias": 40 - dia,
                }
            )
            jogos.append(
                {
                    "casa": fraco,
                    "fora": forte,
                    "gols_casa": 0,
                    "gols_fora": 2,
                    "dias": 40 - dia,
                }
            )
        modelo = ajustar(jogos)
        cartao = avaliar(modelo, forte, fraco, {"casa": 2.5, "empate": 4.5, "fora": 8.0})
        self.assertGreater(cartao["chance"]["casa"], 0.6)
        self.assertEqual(cartao["maisProvavel"], "casa")
        self.assertIsNotNone(cartao["palpite"])
        self.assertEqual(cartao["palpite"]["mercado"], "casa")

    def test_sem_odd_nao_ha_palpite(self):
        grade = tabela_de_placares(1.3, 1.1, -0.04)
        self.assertAlmostEqual(float(grade.sum()), 1.0, places=6)
        jogos = []
        inicio = datetime(2026, 1, 1)
        for dia in range(30):
            jogos.append(
                {
                    "casa": "A",
                    "fora": "B",
                    "gols_casa": 1,
                    "gols_fora": 1,
                    "dias": float(dia),
                }
            )
        modelo = ajustar(jogos)
        cartao = avaliar(modelo, "A", "B", {})
        self.assertIsNone(cartao["palpite"])


if __name__ == "__main__":
    unittest.main()
