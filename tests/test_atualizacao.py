import json
import tempfile
import unittest
from pathlib import Path

from palpitefc.atualizar import gravar_calendario, gravar_proximos
from palpitefc.dados import converter_calendario, converter_football_data_org, hora_de_brasilia, temporada_atual
from palpitefc.retrospectiva import primeira_mudanca


class TesteFusoETemporada(unittest.TestCase):
    def test_hora_inglesa_vira_hora_de_brasilia(self):
        # Horário de verão inglês: 4 horas de diferença.
        self.assertEqual(str(hora_de_brasilia("13/10/2026", "01:00")), "2026-10-12 21:00:00")
        # Inverno inglês: 3 horas.
        self.assertEqual(str(hora_de_brasilia("11/03/2026", "00:30")), "2026-03-10 21:30:00")
        self.assertEqual(str(hora_de_brasilia("01/11/2026", "01:30")), "2026-10-31 22:30:00")
        # Sem hora, o dia publicado não muda.
        self.assertEqual(str(hora_de_brasilia("18/10/2026", "")), "2026-10-18 12:00:00")

    def test_temporada_mais_recente(self):
        self.assertEqual(temporada_atual([{"temporada": "2025"}, {"temporada": "2027"}, {"temporada": "2026"}]), "2027")


class TesteFootballDataOrg(unittest.TestCase):
    def jogo(self, status, utc, casa="SE Palmeiras", fora="CR Flamengo", rodada=31):
        return {"status": status, "utcDate": utc, "matchday": rodada, "homeTeam": {"name": casa}, "awayTeam": {"name": fora}}

    def test_converte_hora_so_quando_confirmada(self):
        jogos = converter_football_data_org(
            {
                "matches": [
                    self.jogo("TIMED", "2026-10-19T00:30:00Z"),
                    self.jogo("SCHEDULED", "2026-10-25T00:00:00Z", "Botafogo FR", "Santos FC", 32),
                    self.jogo("POSTPONED", "2026-07-29T22:00:00Z", "Chapecoense AF", "CR Vasco da Gama", 21),
                ]
            }
        )
        self.assertEqual((jogos[0]["data"], jogos[0]["hora"], jogos[0]["casa"]), ("2026-10-18", "21:30", "Palmeiras"))
        self.assertEqual((jogos[1]["data"], jogos[1]["hora"]), ("2026-10-25", None))
        self.assertTrue(jogos[2]["adiado"])

    def test_acha_o_time_pelo_nome_curto(self):
        jogos = converter_football_data_org(
            {"matches": [{**self.jogo("TIMED", "2026-10-19T00:30:00Z"), "homeTeam": {"name": "Sociedade Esportiva Palmeiras", "shortName": "Palmeiras"}}]}
        )
        self.assertEqual(jogos[0]["casa"], "Palmeiras")

    def test_time_desconhecido_derruba_a_conversao(self):
        with self.assertRaises(ValueError):
            converter_football_data_org({"matches": [self.jogo("TIMED", "2026-10-19T00:30:00Z", "Sport Club do Recife")]})


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

    def test_calendario_curto_e_recusado(self):
        jogos = converter_calendario(
            {"matches": [{"round": "Matchday 1", "date": "2026-01-28", "team1": "SE Palmeiras", "team2": "CR Flamengo"}]}
        )
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "calendario.json"
            with self.assertRaises(ValueError):
                gravar_calendario(jogos, "2026", destino=destino)
            self.assertFalse(destino.exists())

    def test_recusa_pagina_de_erro(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "proximos.csv"
            for ruim in (b"", b"<html><body>Erro 503</body></html>"):
                with self.assertRaises(ValueError):
                    gravar_proximos(ruim, destino)
            self.assertFalse(destino.exists())


if __name__ == "__main__":
    unittest.main()
