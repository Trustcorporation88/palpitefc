import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from palpitefc.dados import carregar_proximos
from palpitefc.model import Modelo
from palpitefc.simulacao import ZONAS, classificacao, simular


def jogo(casa, fora, gols_casa, gols_fora, dia=0):
    return {
        "quando": datetime(2026, 3, 1) + timedelta(days=dia),
        "casa": casa,
        "fora": fora,
        "gols_casa": gols_casa,
        "gols_fora": gols_fora,
    }


class TesteClassificacao(unittest.TestCase):
    def test_pontos_e_desempate(self):
        jogos = [jogo("A", "B", 2, 0), jogo("B", "C", 1, 1, 1), jogo("C", "A", 3, 0, 2), jogo("A", "D", None, None, 3)]
        tabela = classificacao(jogos, ["A", "B", "C", "D"])
        por_time = {linha["id"]: linha for linha in tabela}
        self.assertEqual(por_time["A"]["pts"], 3)
        self.assertEqual(por_time["C"]["pts"], 4)
        self.assertEqual(por_time["B"]["pts"], 1)
        self.assertEqual(por_time["D"]["j"], 0)
        self.assertEqual([linha["id"] for linha in tabela][:2], ["C", "A"])
        self.assertEqual(tabela[0]["posicao"], 1)


class TesteSimulacao(unittest.TestCase):
    def setUp(self):
        times = [f"T{numero:02d}" for numero in range(20)]
        self.modelo = Modelo(
            times=times,
            ataque={time: 0.4 - 0.04 * pos for pos, time in enumerate(times)},
            defesa={time: -0.3 + 0.03 * pos for pos, time in enumerate(times)},
            mando=0.3,
            rho=-0.05,
        )
        self.tabela = [
            {"id": time, "nome": time, "pts": 60 - 3 * pos, "v": 18 - pos, "sg": 20 - 2 * pos, "gp": 40, "j": 30}
            for pos, time in enumerate(times)
        ]
        self.restantes = [(casa, fora) for casa in times for fora in times if casa != fora][:120]

    def test_chances_somam_um(self):
        resultado = simular(self.modelo, self.tabela, self.restantes, simulacoes=2000)
        for linha in resultado["times"]:
            self.assertAlmostEqual(sum(linha["posicoes"]), 1.0, places=6)
        for posicao in range(20):
            self.assertAlmostEqual(sum(linha["posicoes"][posicao] for linha in resultado["times"]), 1.0, places=6)
        self.assertAlmostEqual(sum(linha["zonas"]["titulo"] for linha in resultado["times"]), 1.0, places=6)
        self.assertAlmostEqual(sum(linha["zonas"]["rebaixamento"] for linha in resultado["times"]), 4.0, places=6)

    def test_sem_jogos_a_tabela_fica_como_esta(self):
        resultado = simular(self.modelo, self.tabela, [], simulacoes=500)
        self.assertEqual(resultado["times"][0]["zonas"]["titulo"], 1.0)
        self.assertEqual(resultado["times"][-1]["zonas"]["rebaixamento"], 1.0)
        self.assertEqual(resultado["impacto"], [])

    def test_impacto_aponta_quem_ganha_e_quem_perde(self):
        resultado = simular(self.modelo, self.tabela, self.restantes, simulacoes=2000)
        self.assertLessEqual(len(resultado["impacto"]), 10)
        for confronto in resultado["impacto"]:
            for efeito in confronto["efeitos"]:
                if efeito["zona"] == "rebaixamento":
                    self.assertLessEqual(efeito["seVencer"], efeito["sePerder"])
                else:
                    self.assertGreaterEqual(efeito["seVencer"], efeito["sePerder"])

    def test_zonas_de_2026(self):
        faixas = {zona["id"]: (zona["de"], zona["ate"]) for zona in ZONAS}
        self.assertEqual(faixas["libertadores"], (1, 4))
        self.assertEqual(faixas["prelibertadores"], (5, 5))
        self.assertEqual(faixas["sulamericana"], (6, 11))
        self.assertEqual(faixas["rebaixamento"], (17, 20))


class TesteProximos(unittest.TestCase):
    def test_le_so_a_serie_a(self):
        cabecalho = "Country,League,Date,Time,Home,Away,PSH,PSD,PSA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,BFEH,BFED,BFEA,B365H,B365D,B365A"
        linhas = [
            cabecalho,
            "USA,MLS,18/10/2026,23:30,Miami,Orlando,,,,2.1,3.6,3.5,2.0,3.5,3.4,,,,2.0,3.4,3.4",
            "Brazil,Serie A,18/10/2026,21:00,Palmeiras,Flamengo RJ,,,,2.6,3.4,2.9,2.5,3.3,2.8,,,,2.5,3.3,2.8",
            "Brazil,Serie A,17/10/2026,19:00,Remo,Gremio,,,,3.0,3.3,2.6,2.9,3.2,2.5,,,,,,",
        ]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "proximos.csv"
            caminho.write_text("﻿" + "\n".join(linhas), encoding="utf-8")
            jogos = carregar_proximos(caminho)
            self.assertEqual([jogo["casa"] for jogo in jogos], ["Remo", "Palmeiras"])
            self.assertEqual(jogos[1]["odd_casa"], 2.5)
            self.assertEqual(carregar_proximos(Path(pasta) / "nao-existe.csv"), [])


if __name__ == "__main__":
    unittest.main()
