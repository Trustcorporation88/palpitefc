import asyncio
import io
import unittest
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

from palpitefc import aovivo
from palpitefc.aovivo import AoVivo, ErroDaFonte, converter, ids_desconhecidos, ler_token, rotulo_do_minuto, situacao, times_sem_id


def evento(casa_id, fora_id, gols_casa, gols_fora, status="inprogress", periodo="2nd_half", minuto=12, **extra):
    # Formato do item de /api/v2/events/live/ (EventLiveListItemV2Schema).
    return {
        "id": 7301,
        "league_id": 9,
        "home_team_id": casa_id,
        "home_team": "Mirassol",
        "away_team_id": fora_id,
        "away_team": "Internacional",
        "event_date": "2026-10-16T23:00:00Z",
        "status": status,
        "period": periodo,
        "current_minute": minuto,
        "home_score": gols_casa,
        "away_score": gols_fora,
        "extra_time_score": None,
        "penalty_shootout": None,
        "last_updated": "2026-10-17T00:40:12Z",
        **extra,
    }


PAR = ("Mirassol", "Internacional")
INICIO = datetime(2026, 10, 16, 20, 0)


class TesteConversao(unittest.TestCase):
    def test_traduz_ids_e_hora_de_brasilia(self):
        jogo = converter({"count": 1, "events": [evento(151, 161, 1, 0)]})[PAR]
        self.assertEqual((jogo["golsCasa"], jogo["golsFora"], jogo["situacao"]), (1, 0, "ao vivo"))
        self.assertEqual((jogo["periodo"], jogo["minutoBruto"]), ("2nd_half", 12))
        self.assertEqual(jogo["quando"], INICIO)

    def test_situacoes(self):
        self.assertEqual(situacao("inprogress", "halftime"), "intervalo")
        self.assertEqual(situacao("finished", "FT"), "encerrado")
        self.assertEqual(situacao("notstarted", None), "vai começar")
        self.assertEqual(situacao("postponed", None), "adiado")
        self.assertEqual(situacao("live", "1st_half"), "ao vivo")

    def test_time_desconhecido_e_lixo_ficam_de_fora(self):
        bruto = {"events": [evento(999, 161, 1, 0), "lixo", evento(151, 161, None, 0), evento(151, 161, 1, 0, league_id=8)]}
        self.assertEqual(converter(bruto), {})
        self.assertEqual(ids_desconhecidos(bruto), {999})
        self.assertEqual(converter({"erro": "x"}), {})
        self.assertEqual(converter([]), {})

    def test_antes_do_apito_nao_ha_placar(self):
        jogo = converter({"events": [evento(151, 161, 0, 0, status="notstarted", periodo=None, minuto=None)]})[PAR]
        self.assertEqual((jogo["golsCasa"], jogo["situacao"]), (None, "vai começar"))

    def test_prorrogacao_entra_no_placar(self):
        jogo = converter({"events": [evento(151, 161, 1, 1, periodo="extra_time", extra_time_score={"home": 1, "away": 0})]})[PAR]
        self.assertEqual((jogo["golsCasa"], jogo["golsFora"]), (2, 1))

    def test_lista_paginada_em_results(self):
        self.assertIn(PAR, converter({"results": [evento(151, 161, 2, 2, status="finished", periodo="FT")]}))

    def test_times_sem_id(self):
        self.assertEqual(times_sem_id(["Mirassol", "Novo FC"]), ["Novo FC"])


class TesteMinuto(unittest.TestCase):
    def test_rotulos(self):
        self.assertEqual(rotulo_do_minuto("1st_half", 30, None), "30")
        self.assertEqual(rotulo_do_minuto("1st_half", 47, None), "45+2")
        self.assertEqual(rotulo_do_minuto("2nd_half", 12, True), "57")
        self.assertEqual(rotulo_do_minuto("2nd_half", 48, True), "90+3")
        self.assertEqual(rotulo_do_minuto("2nd_half", 67, False), "67")
        self.assertEqual(rotulo_do_minuto("2nd_half", 93, False), "90+3")
        self.assertIsNone(rotulo_do_minuto("halftime", 45, None))
        self.assertIsNone(rotulo_do_minuto("2nd_half", "67", True))

    def sequencia(self, minutos, relogio=None):
        painel = PainelFalso([(PAR, INICIO, True)])
        respostas = iter([{"events": [evento(151, 161, 0, 0, minuto=minuto)]} for minuto in minutos])
        momentos = iter(relogio or [INICIO + timedelta(minutes=70)] * len(minutos))
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: next(respostas), relogio=lambda: next(momentos))
        rotulos = []
        for _ in minutos:
            vivo.consultar()
            rotulos.append(vivo.jogos[PAR]["minuto"])
        return rotulos

    def test_acrescimo_do_segundo_tempo_contado_do_periodo(self):
        # Pela doc: 44 e 45 do período são 89' e 90'; 46 é o 1º minuto de acréscimo.
        self.assertEqual(self.sequencia([1, 44, 45, 46, 48]), ["46", "89", "90", "90+1", "90+3"])

    def test_contado_do_apito_inicial(self):
        self.assertEqual(self.sequencia([45, 46, 89, 92]), ["45", "46", "89", "90+2"])

    def test_servidor_reiniciado_no_acrescimo(self):
        # Primeira olhada com 47 e 107 minutos depois do início: é acréscimo, não o 47'.
        self.assertEqual(self.sequencia([47], relogio=[INICIO + timedelta(minutes=107)]), ["90+2"])

    def test_minuto_nao_volta(self):
        self.assertEqual(self.sequencia([60, 59]), ["60", "60"])


class PainelFalso:
    def __init__(self, inicios, restantes=None):
        self._inicios = inicios
        self.restantes = restantes if restantes is not None else [par for par, _, _ in inicios]
        self.pedidos = []

    def inicios_pendentes(self):
        return self._inicios

    def se_terminar_assim(self, placares):
        self.pedidos.append(dict(placares))
        return {"jogos": len(placares), "times": []}


class TesteJanela(unittest.TestCase):
    def vivo(self, inicios, **extra):
        return AoVivo(PainelFalso(inicios, **extra), "t" * 32, baixar=lambda url: {})

    def test_ritmo_de_jogo_perto_do_inicio(self):
        vivo = self.vivo([(PAR, INICIO, True)])
        self.assertEqual(vivo.janela(INICIO + timedelta(minutes=30)), ("jogo", aovivo.INTERVALO_NO_JOGO))
        self.assertEqual(vivo.janela(INICIO - timedelta(minutes=5))[0], "jogo")

    def test_sentinela_no_resto_do_dia_sem_passar_do_inicio(self):
        vivo = self.vivo([(PAR, INICIO, True)])
        self.assertEqual(vivo.janela(INICIO - timedelta(hours=3)), ("sentinela", aovivo.INTERVALO_SENTINELA))
        # A olhada de 10 em 10 minutos não atravessa o começo da janela.
        self.assertEqual(vivo.janela(INICIO - timedelta(minutes=13)), ("sentinela", 180))
        self.assertEqual(vivo.janela(INICIO + timedelta(hours=3))[0], "sentinela")

    def test_madrugada_dorme_ate_as_onze(self):
        vivo = self.vivo([(PAR, INICIO, True)])
        self.assertEqual(vivo.janela(datetime(2026, 10, 16, 10, 0)), (None, 3600))
        self.assertEqual(vivo.janela(datetime(2026, 10, 16, 10, 59, 30)), (None, 30))
        self.assertEqual(vivo.janela(datetime(2026, 10, 16, 1, 0)), (None, 3600))

    def test_sem_hora_confirmada_olha_a_cada_dois_minutos_por_alguns_dias(self):
        vivo = self.vivo([(PAR, INICIO.replace(hour=12), False)])
        self.assertEqual(vivo.janela(INICIO.replace(hour=15)), ("dia", aovivo.INTERVALO_SEM_HORA))
        # O openfootball põe a rodada inteira no primeiro dia: o jogo pode ser no domingo.
        self.assertEqual(vivo.janela(INICIO.replace(hour=15) + timedelta(days=2))[0], "dia")
        self.assertEqual(vivo.janela(INICIO.replace(hour=15) + timedelta(days=5))[0], "sentinela")
        self.assertIsNone(vivo.janela(INICIO.replace(hour=9))[0])

    def test_campeonato_acabado_nao_consulta(self):
        self.assertEqual(self.vivo([], restantes=[]).janela(INICIO), (None, aovivo.ESPERA_MAXIMA))

    def test_jogo_atrasado_segue_ate_o_apito(self):
        painel = PainelFalso([(PAR, INICIO, True)])
        agora = [INICIO + timedelta(minutes=149)]
        respostas = iter([
            {"events": [evento(151, 161, 1, 0, minuto=35)]},
            {"events": [evento(151, 161, 1, 1, minuto=44)]},
            {"events": [evento(151, 161, 1, 1, status="finished", periodo="FT", minuto=None)]},
        ])
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: next(respostas), relogio=lambda: agora[0])
        vivo.consultar()
        agora[0] = INICIO + timedelta(minutes=165)
        # Passou das 2h30, mas a fonte ainda mostra o jogo em andamento.
        self.assertEqual(vivo.janela(agora[0]), ("jogo", aovivo.INTERVALO_NO_JOGO))
        vivo.consultar()
        self.assertEqual(vivo.estado()["jogos"][0]["golsFora"], 1)
        vivo.consultar()
        self.assertEqual(vivo.estado()["jogos"][0]["situacao"], "encerrado")
        self.assertEqual(vivo.janela(agora[0])[0], "sentinela")

    def test_teto_de_quatro_horas(self):
        tarde = INICIO.replace(hour=14)
        painel = PainelFalso([(PAR, tarde, True)])
        agora = [tarde]
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: {"events": [evento(151, 161, 0, 0, status="delayed", periodo=None, minuto=None)]}, relogio=lambda: agora[0])
        vivo.consultar()
        agora[0] = tarde + timedelta(hours=4, minutes=1)
        vivo.ultima_consulta = agora[0]
        vivo._vistos[PAR]["visto"] = agora[0]
        self.assertEqual(vivo.janela(agora[0])[0], "sentinela")

    def test_jogo_fora_do_calendario_achado_pela_sentinela(self):
        # Remarcado: o calendário diz 16h, o jogo começa às 18h30.
        painel = PainelFalso([(PAR, INICIO.replace(hour=16), True)])
        agora = INICIO.replace(hour=18, minute=40)
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: {"events": [evento(151, 161, 0, 0, periodo="1st_half", minuto=8)]}, relogio=lambda: agora)
        self.assertEqual(vivo.janela(agora)[0], "sentinela")
        vivo.consultar()
        self.assertEqual(vivo.janela(agora), ("jogo", aovivo.INTERVALO_NO_JOGO))


class TesteConsulta(unittest.TestCase):
    def test_gol_refaz_a_tabela_e_placar_igual_nao(self):
        painel = PainelFalso([(PAR, INICIO, True)])
        respostas = iter([
            {"events": [evento(151, 161, 0, 0, periodo="1st_half", minuto=10)]},
            {"events": [evento(151, 161, 0, 0, periodo="1st_half", minuto=20)]},
            {"events": [evento(151, 161, 1, 0, periodo="1st_half", minuto=31)]},
            {"events": []},
        ])
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: next(respostas), relogio=lambda: INICIO)
        self.assertTrue(vivo.consultar())
        self.assertFalse(vivo.consultar())
        self.assertTrue(vivo.consultar())
        self.assertEqual(painel.pedidos[-1], {PAR: (1, 0)})
        # Saiu da lista ao vivo: fica o último placar visto.
        self.assertFalse(vivo.consultar())
        estado = vivo.estado()
        self.assertEqual((estado["jogos"][0]["golsCasa"], estado["jogos"][0]["casaNome"]), (1, "Mirassol"))
        self.assertEqual(estado["seTerminarAssim"], {"jogos": 1, "times": []})

    def test_vai_comecar_nao_entra_na_tabela(self):
        painel = PainelFalso([(PAR, INICIO, True)])
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: {"events": [evento(151, 161, 0, 0, status="notstarted", periodo=None)]}, relogio=lambda: INICIO)
        self.assertFalse(vivo.consultar())
        self.assertEqual((vivo.estado()["jogos"], painel.pedidos), ([], []))
        # Mas a consulta já fica no ritmo de jogo.
        self.assertEqual(vivo.janela(INICIO + timedelta(hours=3))[0], "jogo")

    def test_jogo_fora_dos_pendentes_e_ignorado(self):
        painel = PainelFalso([(PAR, INICIO, True)])
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: {"events": [evento(162, 160, 2, 0)]})
        self.assertFalse(vivo.consultar())
        self.assertEqual(vivo.estado()["jogos"], [])

    def test_placar_parado_nao_fica_ao_vivo(self):
        painel = PainelFalso([(PAR, INICIO, True)])
        agora = [INICIO + timedelta(minutes=60)]
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: {"events": [evento(151, 161, 1, 0)]}, relogio=lambda: agora[0])
        vivo.consultar()
        self.assertEqual(vivo.estado()["jogos"][0]["situacao"], "ao vivo")
        # A fonte para de responder (ou o jogo some da lista sem o apito final).
        agora[0] += timedelta(minutes=4)
        jogo = vivo.estado()["jogos"][0]
        self.assertEqual((jogo["situacao"], jogo["minuto"], jogo["vistoEm"]), ("sem atualização", None, "2026-10-16T21:00:00"))

    def test_encerrado_nao_envelhece(self):
        painel = PainelFalso([(PAR, INICIO, True)])
        agora = [INICIO + timedelta(minutes=115)]
        vivo = AoVivo(painel, "t" * 32, baixar=lambda url: {"events": [evento(151, 161, 2, 1, status="finished", periodo="FT")]}, relogio=lambda: agora[0])
        vivo.consultar()
        agora[0] += timedelta(days=2)
        self.assertEqual(vivo.estado()["jogos"][0]["situacao"], "encerrado")

    def test_recupera_encerrados_depois_do_deploy(self):
        painel = PainelFalso([(PAR, INICIO, True)], restantes=[PAR, ("Santos", "Flamengo RJ")])
        pedidos = []

        def baixar(url):
            pedidos.append(url)
            return {"results": [
                evento(151, 161, 2, 1, status="finished", periodo="FT"),
                evento(165, 160, 0, 0, status="notstarted", periodo=None),
            ]}

        vivo = AoVivo(painel, "t" * 32, baixar=baixar, relogio=lambda: INICIO + timedelta(days=1))
        self.assertTrue(vivo.recuperar())
        self.assertIn("status=finished", pedidos[0])
        self.assertIn("date_from=2026-10-13&date_to=2026-10-18", pedidos[0])
        self.assertEqual(list(vivo.jogos), [PAR])
        self.assertEqual(painel.pedidos[-1], {PAR: (2, 1)})
        self.assertEqual(vivo.estado()["jogos"][0]["quando"], "2026-10-16T20:00:00")


class TesteErros(unittest.TestCase):
    TOKEN = "segredo-de-teste-1234567890"

    def chamar_com(self, erro):
        with mock.patch.object(aovivo.urllib.request.OpenerDirector, "open", side_effect=erro):
            with self.assertRaises(ErroDaFonte) as contexto:
                aovivo._baixar_da_bzzoiro(self.TOKEN, aovivo.URL_AO_VIVO)
        return contexto.exception

    def test_401_e_429(self):
        nao_autorizado = urllib.error.HTTPError(aovivo.URL_AO_VIVO, 401, "Unauthorized", {}, io.BytesIO(b"<html>401</html>"))
        erro = self.chamar_com(nao_autorizado)
        self.assertEqual((str(erro), erro.esperar), ("HTTP 401", 0.0))
        cota = urllib.error.HTTPError(aovivo.URL_AO_VIVO, 429, "Too Many", {"Retry-After": "120"}, io.BytesIO(b"{}"))
        erro = self.chamar_com(cota)
        self.assertEqual((str(erro), erro.esperar), ("HTTP 429", 120.0))
        self.assertNotIn(self.TOKEN, str(erro))

    def test_falha_de_rede(self):
        self.assertEqual(str(self.chamar_com(urllib.error.URLError("sem rede"))), "URLError")

    def test_rodar_nao_cai_com_erro(self):
        painel = PainelFalso([(PAR, INICIO, True)])

        def falha(url):
            raise ErroDaFonte("HTTP 503")

        vivo = AoVivo(painel, "t" * 32, baixar=falha, relogio=lambda: INICIO)

        async def uma_volta():
            tarefa = asyncio.create_task(vivo.rodar())
            await asyncio.sleep(0.05)
            tarefa.cancel()

        asyncio.run(uma_volta())
        self.assertEqual((vivo.erro, vivo.consultando), ("HTTP 503", True))


class TesteToken(unittest.TestCase):
    def test_formato(self):
        with mock.patch.dict(aovivo.os.environ, {"BSD_TOKEN": "  abcdefghijklmnop1234  "}):
            self.assertEqual(ler_token(), "abcdefghijklmnop1234")
        for ruim in ("", "curto", "tem espaço no meio 1234567890", "abc\ndef1234567890123"):
            with mock.patch.dict(aovivo.os.environ, {"BSD_TOKEN": ruim}):
                self.assertIsNone(ler_token())


class TesteSeTerminarAssim(unittest.TestCase):
    def test_placar_de_agora_entra_na_tabela(self):
        from palpitefc.servico import painel

        p = painel()
        casa, fora = p.restantes[0]
        antes = {linha["id"]: linha for linha in p.simulacao["times"]}
        resultado = p.se_terminar_assim({(casa, fora): (3, 0), ("Nao", "Existe"): (1, 1)})
        self.assertEqual(resultado["jogos"], 1)
        por_time = {linha["id"]: linha for linha in resultado["times"]}
        self.assertEqual(por_time[casa]["pts"], antes[casa]["pts"] + 3)
        self.assertEqual(por_time[fora]["pts"], antes[fora]["pts"])
        self.assertAlmostEqual(sum(linha["zonas"]["titulo"] for linha in resultado["times"]), 1.0, places=6)
        self.assertIsNone(p.se_terminar_assim({("Nao", "Existe"): (1, 1)}))

    def test_inicios_dos_pendentes(self):
        from palpitefc.servico import painel

        p = painel()
        inicios = p.inicios_pendentes()
        self.assertTrue(inicios)
        self.assertTrue(all(isinstance(quando, datetime) and isinstance(certo, bool) for _, quando, certo in inicios))
        self.assertTrue({par for par, _, _ in inicios} <= set(p.restantes))
        # Par sem hora não se repete; com hora, só se as duas fontes divergirem.
        sem_hora = [par for par, _, certo in inicios if not certo]
        self.assertEqual(len(sem_hora), len(set(sem_hora)))
        self.assertFalse(set(sem_hora) & {par for par, _, certo in inicios if certo})


if __name__ == "__main__":
    unittest.main()
