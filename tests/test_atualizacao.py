import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

from palpitefc import atualizar
from palpitefc.atualizar import _opcional, atualizar_calendario, gravar_calendario, gravar_proximos
from palpitefc.dados import (
    NOMES_OPENFOOTBALL,
    converter_calendario,
    converter_football_data_org,
    hora_de_brasilia,
    outra_leitura_da_madrugada_inglesa,
    promovidos,
    temporada_atual,
)
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

    def test_madrugada_inglesa_ambigua(self):
        # 25/10/2026: o Reino Unido atrasa o relógio e 01:00 acontece duas vezes.
        lido = hora_de_brasilia("25/10/2026", "01:00")
        self.assertEqual(str(lido), "2026-10-24 21:00:00")
        self.assertEqual(str(outra_leitura_da_madrugada_inglesa(lido)), "2026-10-24 22:00:00")
        self.assertIsNone(outra_leitura_da_madrugada_inglesa(hora_de_brasilia("18/10/2026", "21:00")))


def temporada_cheia(ano, times):
    return [
        {"temporada": ano, "casa": casa, "fora": fora}
        for casa, fora in zip(times, times[1:] + times[:1])
    ]


class TesteViradaDeTemporada(unittest.TestCase):
    TIMES = [f"Time{numero:02d}" for numero in range(20)]

    def test_so_vira_com_os_vinte_times(self):
        jogos = temporada_cheia("2026", self.TIMES) + [
            {"temporada": "2027", "casa": "Time00", "fora": "Time01"},
            {"temporada": "2027", "casa": "Subiu", "fora": "Time02"},
        ]
        self.assertEqual(temporada_atual(jogos), "2026")
        novos = self.TIMES[3:] + ["Subiu", "Outro"]
        self.assertEqual(temporada_atual(jogos, set(novos)), "2027")
        self.assertEqual(temporada_atual(temporada_cheia("2027", self.TIMES)), "2027")

    def test_promovido_que_so_esta_no_calendario(self):
        jogos = temporada_cheia("2026", self.TIMES) + [{"temporada": "2027", "casa": "Time00", "fora": "Time01"}]
        participantes = self.TIMES[2:] + ["Subiu", "Outro"]
        self.assertEqual(promovidos(jogos, "2027"), frozenset())
        self.assertEqual(promovidos(jogos, "2027", participantes), {"Subiu", "Outro"})


def calendario_valido(quantos=300):
    times = sorted(set(NOMES_OPENFOOTBALL.values()))
    pares = [(casa, fora) for casa in times for fora in times if casa != fora][:quantos]
    return [
        {"rodada": 1 + numero % 38, "data": "2026-10-17", "hora": None, "casa": casa, "fora": fora, "adiado": False}
        for numero, (casa, fora) in enumerate(pares)
    ]


class TesteCalendarioOficial(unittest.TestCase):
    CHAVE = "a" * 32

    def test_falha_passageira_mantem_o_calendario_oficial(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "calendario.json"
            gravar_calendario(calendario_valido(), "2026", "football-data.org", destino)
            antes = destino.read_bytes()
            with mock.patch.object(atualizar, "calendario_football_data_org", side_effect=OSError("fora do ar")), \
                 mock.patch.object(atualizar, "calendario_openfootball") as aberto, redirect_stdout(io.StringIO()):
                quantos, fonte = atualizar_calendario("2026", self.CHAVE, destino)
            self.assertEqual((quantos, fonte), (300, "football-data.org"))
            aberto.assert_not_called()
            self.assertEqual(destino.read_bytes(), antes)

    def test_sem_calendario_oficial_usa_o_aberto(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "calendario.json"
            with mock.patch.object(atualizar, "calendario_football_data_org", side_effect=TypeError("lista")), \
                 mock.patch.object(atualizar, "calendario_openfootball", return_value=calendario_valido()), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(atualizar_calendario("2026", self.CHAVE, destino), (300, "openfootball"))

    def test_chave_fora_do_formato_nem_e_usada(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "calendario.json"
            with mock.patch.object(atualizar, "calendario_football_data_org") as oficial, \
                 mock.patch.object(atualizar, "calendario_openfootball", return_value=calendario_valido()), \
                 redirect_stdout(io.StringIO()) as saida:
                atualizar_calendario("2026", "abc\ndef" * 4, destino)
            oficial.assert_not_called()
            self.assertNotIn("abc", saida.getvalue())

    def test_erro_sigiloso_nao_mostra_a_mensagem(self):
        segredo = "b" * 32

        def falha():
            raise ValueError(f"Invalid header value b'{segredo}'")

        with redirect_stdout(io.StringIO()) as saida:
            self.assertIsNone(_opcional("Calendário", falha, sigiloso=True))
            self.assertIsNone(_opcional("Outra fonte", lambda: None.algo))
        self.assertNotIn(segredo, saida.getvalue())
        self.assertIn("ValueError", saida.getvalue())
        self.assertIn("AttributeError", saida.getvalue())


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

    def test_dois_clubes_no_mesmo_nome_derrubam_a_conversao(self):
        botafogo_sp = {**self.jogo("TIMED", "2026-10-19T00:30:00Z"), "homeTeam": {"name": "Botafogo FC", "shortName": "Botafogo"}}
        botafogo_rj = self.jogo("TIMED", "2026-10-20T00:30:00Z", "Botafogo FR", "Santos FC")
        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            converter_football_data_org({"matches": [botafogo_sp, botafogo_rj]})

    def test_time_sem_dados_derruba_a_conversao(self):
        with self.assertRaises(ValueError):
            converter_football_data_org({"matches": [{**self.jogo("TIMED", "2026-10-19T00:30:00Z"), "homeTeam": None}]})


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
