import math
import unittest

from palpitefc.metricas import brier, calibracao, log_loss, notas, rps
from palpitefc.odds import margem, proporcional, shin


class TesteNotas(unittest.TestCase):
    def test_rps_premia_quem_erra_perto(self):
        certa = {"casa": 1.0, "empate": 0.0, "fora": 0.0}
        self.assertAlmostEqual(rps(certa, "casa"), 0.0)
        empate = {"casa": 0.0, "empate": 1.0, "fora": 0.0}
        fora = {"casa": 0.0, "empate": 0.0, "fora": 1.0}
        self.assertAlmostEqual(rps(empate, "casa"), 0.5)
        self.assertAlmostEqual(rps(fora, "casa"), 1.0)

    def test_rps_de_chute_uniforme(self):
        terco = {"casa": 1 / 3, "empate": 1 / 3, "fora": 1 / 3}
        self.assertAlmostEqual(rps(terco, "empate"), 1 / 9)
        self.assertAlmostEqual(rps(terco, "casa"), 5 / 18)

    def test_brier_e_log_loss(self):
        chance = {"casa": 0.5, "empate": 0.3, "fora": 0.2}
        self.assertAlmostEqual(brier(chance, "casa"), 0.25 + 0.09 + 0.04)
        self.assertAlmostEqual(log_loss(chance, "fora"), -math.log(0.2))
        self.assertEqual(set(notas(chance, "casa")), {"rps", "brier", "logLoss"})

    def test_calibracao_agrupa_por_faixa(self):
        linhas = calibracao([(0.05, False), (0.08, True), (0.55, True), (0.99, True), (1.0, True)])
        self.assertEqual([linha["casos"] for linha in linhas], [2, 1, 2])
        self.assertAlmostEqual(linhas[0]["observada"], 0.5)
        self.assertEqual(linhas[-1]["de"], 0.9)


class TesteOdds(unittest.TestCase):
    ODDS = {"casa": 1.5, "empate": 4.2, "fora": 7.0}

    def test_margem(self):
        self.assertAlmostEqual(margem(self.ODDS), 1 / 1.5 + 1 / 4.2 + 1 / 7.0 - 1)
        self.assertIsNone(margem({"casa": 1.5, "empate": None, "fora": 7.0}))

    def test_shin_soma_um_e_corta_mais_da_zebra(self):
        justa = shin(self.ODDS)
        simples = proporcional(self.ODDS)
        self.assertAlmostEqual(sum(justa.values()), 1.0)
        self.assertAlmostEqual(sum(simples.values()), 1.0)
        self.assertGreater(justa["casa"], simples["casa"])
        self.assertLess(justa["fora"], simples["fora"])

    def test_sem_margem_nao_mexe(self):
        justas = {"casa": 2.0, "empate": 4.0, "fora": 4.0}
        self.assertAlmostEqual(shin(justas)["casa"], 0.5)
        self.assertIsNone(shin({}))


if __name__ == "__main__":
    unittest.main()
