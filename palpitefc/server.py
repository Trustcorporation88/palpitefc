"""Site do PalpiteFC. A conta roda aqui; o navegador só mostra."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from palpitefc.aovivo import DESLIGADO, AoVivo, ler_token, times_sem_id
from palpitefc.conferir_tabela import ARQUIVO as ARQUIVO_CONFERENCIA
from palpitefc.dados import ARQUIVO, ARQUIVO_CALENDARIO, ARQUIVO_PROXIMOS
from palpitefc.retrospectiva import ARQUIVO as ARQUIVO_RETRO
from palpitefc.servico import painel

WEB = Path(__file__).resolve().parent.parent / "web"
# Os dados só mudam a cada deploy; cinco minutos de cache poupam o servidor.
CACHE_API = "public, max-age=300"
# CSS e JS levam o hash do conteúdo na URL, então podem ficar um dia em cache.
CACHE_ESTATICO = "public, max-age=86400"


# Placar ao vivo: só existe com BSD_TOKEN no ambiente do servidor.
ao_vivo: AoVivo | None = None


@asynccontextmanager
async def ciclo(_: FastAPI):
    global ao_vivo
    token = ler_token()
    tarefa = None
    if token:
        ao_vivo = AoVivo(painel(), token)
        tarefa = asyncio.create_task(ao_vivo.rodar())
    else:
        painel()
    yield
    if tarefa:
        tarefa.cancel()


app = FastAPI(title="PalpiteFC", lifespan=ciclo)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def cabecalhos(request, chamar):
    resposta = await chamar(request)
    pedida = request.query_params.get("v")
    if pedida is not None and pedida != versao():
        # Na troca de deploy, o pedido da versão nova pode cair no contêiner
        # velho (ou o contrário). Essa resposta não pode ficar em cache.
        resposta.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/api/") and resposta.status_code == 200:
        resposta.headers.setdefault("Cache-Control", CACHE_API)
    elif request.url.path.startswith("/static/") and resposta.status_code == 200:
        resposta.headers.setdefault("Cache-Control", CACHE_ESTATICO)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resposta


@app.get("/api/saude")
def saude(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    estado = ao_vivo.estado() if ao_vivo else DESLIGADO
    return {
        "ok": True,
        "atualizadoEm": painel().ultimo_jogo.isoformat(timespec="minutes"),
        "aoVivo": {chave: estado[chave] for chave in ("ativo", "consultando", "ultimaConsulta", "erro")}
        | {
            "jogos": len(estado["jogos"]),
            # Na virada do ano: time novo sem id da Bzzoiro não aparece ao vivo.
            "timesSemId": times_sem_id(painel().times_temporada),
            "idsDesconhecidos": sorted(ao_vivo.desconhecidos) if ao_vivo else [],
        },
    }


@app.get("/api/aovivo")
def placar_ao_vivo(response: Response) -> dict:
    # Muda a cada gol: sem cache.
    response.headers["Cache-Control"] = "no-store"
    return ao_vivo.estado() if ao_vivo else DESLIGADO


@app.get("/api/inicio")
def inicio() -> dict:
    return painel().inicio()


@app.get("/api/times")
def times() -> dict:
    return {"times": painel().times()}


@app.get("/api/tabela")
def tabela() -> dict:
    return painel().tabela()


@app.get("/api/conta")
def conta() -> dict:
    return painel().conta()


@app.get("/api/time/{time}")
def do_time(time: str) -> dict:
    try:
        return painel().do_time(time)
    except KeyError:
        raise HTTPException(status_code=404, detail="Time fora do campeonato desta temporada") from None


@app.get("/api/simular")
def simular(casa: str, fora: str) -> dict:
    try:
        return painel().simular(casa, fora)
    except KeyError:
        raise HTTPException(status_code=400, detail="Escolha dois times diferentes do campeonato") from None


@app.get("/api/forca")
def forca() -> dict:
    return {"times": painel().forca()}


@cache
def versao() -> str:
    """Muda quando muda o CSS, o JS ou os dados. Vai na URL dos estáticos e
    das chamadas da API, para o cache do navegador nunca misturar versões."""
    resumo = hashlib.sha256()
    arquivos = (
        WEB / "app.js",
        WEB / "estilos.css",
        ARQUIVO,
        ARQUIVO_PROXIMOS,
        ARQUIVO_CALENDARIO,
        ARQUIVO_RETRO,
        ARQUIVO_CONFERENCIA,
    )
    for arquivo in arquivos:
        if arquivo.exists():
            resumo.update(arquivo.read_bytes())
    return resumo.hexdigest()[:10]


@cache
def pagina_inicial() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8").replace("{{versao}}", versao())


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def raiz() -> HTMLResponse:
    return HTMLResponse(pagina_inicial(), headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(WEB / "favicon.svg", media_type="image/svg+xml", headers={"Cache-Control": CACHE_ESTATICO})


app.mount("/static", StaticFiles(directory=WEB), name="static")
