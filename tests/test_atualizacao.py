import tempfile
import unittest
from pathlib import Path

from palpitefc.atualizar import gravar_proximos
from palpitefc.retrospectiva import primeira_mudanca


class TesteRetrospectivaIncremental(unittest.TestCase):
    ANTES = {
        "2026-05-01T16:00|A|B": [1, 0, 2.0, 3.2, 4.0],
        "2026-05-08T16:00|B|C": [2, 2, 2.5, 3.1, 3.0],
    }

    def test_sem_mudanca(self):
        self.assertIsNone(primeira_mudanca(dict(self.ANTES), self.ANTES))

    def test_jogo_novo_no_fim(self):
        agora = {**self.ANTES, "2026-05-15T16:00|C|A": [0, 1, 2.2, 3.3, 3.4]}
        self.assertEqual(primeira_mudanca(agora, self.ANTES), "2026-05-15T16:00")

    def test_placar_ou_odd_corrigido_volta_ao_jogo_antigo(self):
        agora = {**self.ANTES, "2026-05-01T16:00|A|B": [1, 0, 2.0, 3.2, 4.1]}
        agora["2026-05-15T16:00|C|A"] = [0, 1, 2.2, 3.3, 3.4]
        self.assertEqual(primeira_mudanca(agora, self.ANTES), "2026-05-01T16:00")

    def test_jogo_que_mudou_de_data(self):
        agora = {"2026-05-01T16:00|A|B": [1, 0, 2.0, 3.2, 4.0], "2026-05-09T20:00|B|C": [2, 2, 2.5, 3.1, 3.0]}
        self.assertEqual(primeira_mudanca(agora, self.ANTES), "2026-05-08T16:00")


class TesteProximosBaixados(unittest.TestCase):
    def test_guarda_so_a_serie_a(self):
        csv = (
            "﻿Country,League,Date,Time,Home,Away,AvgH,AvgD,AvgA\n"
            "USA,MLS,18/10/2026,23:30,Miami,Orlando,2.0,3.5,3.4\n"
            "Brazil,Serie A,18/10/2026,21:00,Palmeiras,Flamengo RJ,2.5,3.3,2.8\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "proximos.csv"
            self.assertEqual(gravar_proximos(csv, destino), 1)
            self.assertNotIn("Miami", destino.read_text(encoding="utf-8"))

    def test_recusa_pagina_de_erro(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "proximos.csv"
            for ruim in (b"", b"<html><body>Erro 503</body></html>"):
                with self.assertRaises(ValueError):
                    gravar_proximos(ruim, destino)
            self.assertFalse(destino.exists())


if __name__ == "__main__":
    unittest.main()
