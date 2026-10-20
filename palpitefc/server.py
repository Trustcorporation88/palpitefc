"""Site do PalpiteFC. A conta roda aqui; o navegador só mostra."""

import asyncio
import hashlib
import hmac
import html
import os
import re
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from palpitefc.aovivo import DESLIGADO, AoVivo, ler_token, times_sem_id
from palpitefc import contas
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


SEM_CACHE = {"Cache-Control": "private, no-store"}
# Só o aviso de saúde fica aberto: todo o resto da API é de quem entrou e aceitou o termo.
ABERTAS = {"/api/saude", "/api/conferencia"}


def _token_do_pedido(request: Request) -> str:
    cabecalho = request.headers.get("authorization", "")
    return cabecalho[7:].strip() if cabecalho.lower().startswith("bearer ") else ""


async def _barrar(request) -> JSONResponse | None:
    if not contas.configurado():
        return JSONResponse({"erro": "login não configurado no servidor"}, status_code=503, headers=SEM_CACHE)
    token = _token_do_pedido(request)
    try:
        liberado = bool(token) and await asyncio.to_thread(contas.pode_ver, token)
    except contas.ContaIndisponivel:
        return JSONResponse({"erro": "login indisponível agora"}, status_code=503, headers=SEM_CACHE)
    if not liberado:
        return JSONResponse({"erro": "entre e aceite os termos"}, status_code=401, headers=SEM_CACHE)
    return None


@app.middleware("http")
async def cabecalhos(request, chamar):
    protegida = request.url.path.startswith("/api/") and request.url.path not in ABERTAS
    if protegida:
        barrada = await _barrar(request)
        if barrada is not None:
            return barrada
    resposta = await chamar(request)
    if protegida:
        resposta.headers["Cache-Control"] = "private, no-store"
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


EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MOTIVOS_DA_CONTA = {
    "email_exists": (409, "Já existe conta com este e-mail."),
    "user_already_exists": (409, "Já existe conta com este e-mail."),
    "weak_password": (400, "A senha precisa de 8 caracteres ou mais."),
    "validation_failed": (400, "O e-mail ou a senha não são aceitos pelo Supabase."),
}


@app.get("/api/admin/eu")
def sou_admin(request: Request) -> dict:
    return {"admin": contas.eh_admin(contas.usuario_de(_token_do_pedido(request)))}


@app.post("/api/admin/contas", status_code=201)
def criar_conta(request: Request, corpo: dict = Body(...)) -> dict:
    # O corpo vem como dict, sem o validador do FastAPI: um erro de validação
    # devolveria a senha de volta na resposta.
    if not contas.eh_admin(contas.usuario_de(_token_do_pedido(request))):
        raise HTTPException(status_code=403, detail="Só o administrador cria contas.")
    email, senha = corpo.get("email"), corpo.get("senha")
    if not isinstance(email, str) or not isinstance(senha, str):
        raise HTTPException(status_code=400, detail="Informe o e-mail e a senha.")
    email = email.strip().lower()
    if not EMAIL.fullmatch(email):
        raise HTTPException(status_code=400, detail="E-mail inválido.")
    if len(senha) < 8:
        raise HTTPException(status_code=400, detail="A senha precisa de 8 caracteres ou mais.")
    try:
        resultado = contas.criar_conta(email, senha)
    except contas.ContaIndisponivel:
        raise HTTPException(status_code=503, detail="Não deu para falar com o Supabase agora.") from None
    if resultado != "criada":
        status, detalhe = MOTIVOS_DA_CONTA.get(resultado, (400, "Não deu para criar a conta."))
        raise HTTPException(status_code=status, detail=detalhe)
    return {"ok": True, "email": email}


def _resultado(placar: tuple[int, int]) -> str:
    return "casa" if placar[0] > placar[1] else "fora" if placar[1] > placar[0] else "empate"


@app.get("/api/conferencia")
def conferencia(request: Request) -> dict:
    """Jogos encerrados desde o começo da temporada, com a chance que o site deu antes do apito.

    Só para conferir o modelo: exige o token CONFERENCIA_TOKEN no cabeçalho
    X-Conferencia-Token. Não tem placar ao vivo, só jogos já encerrados.
    """
    esperado = os.environ.get("CONFERENCIA_TOKEN", "").strip()
    recebido = request.headers.get("x-conferencia-token", "")
    if not esperado or not hmac.compare_digest(recebido.encode("utf-8"), esperado.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Token de conferência inválido.")
    jogos = []
    if ao_vivo:
        for (casa, fora), jogo in ao_vivo.jogos.items():
            if jogo["situacao"] != "encerrado" or jogo["golsCasa"] is None:
                continue
            try:
                cartao = painel().simular(casa, fora)
            except KeyError:
                continue
            placar = (jogo["golsCasa"], jogo["golsFora"])
            jogos.append(
                {
                    "quando": jogo["quando"].isoformat(timespec="minutes") if jogo["quando"] else None,
                    "casa": casa,
                    "fora": fora,
                    "placar": f"{placar[0]}–{placar[1]}",
                    "chance": cartao["chance"],
                    "maisProvavel": cartao["maisProvavel"],
                    "resultado": _resultado(placar),
                    "acertou": cartao["maisProvavel"] == _resultado(placar),
                }
            )
    jogos.sort(key=lambda linha: linha["quando"] or "")
    return {"jogos": jogos, "acertos": sum(linha["acertou"] for linha in jogos), "total": len(jogos)}


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
    # A chave pública do Supabase vai para o navegador de qualquer forma; a secreta nunca sai do servidor.
    url = os.environ.get("SUPABASE_URL", "").strip()
    chave = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    return (
        (WEB / "index.html")
        .read_text(encoding="utf-8")
        .replace("{{versao}}", versao())
        .replace("{{supabase_url}}", html.escape(url))
        .replace("{{supabase_chave}}", html.escape(chave))
        .replace("{{termo_versao}}", html.escape(contas.VERSAO_DO_TERMO))
    )


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def raiz() -> HTMLResponse:
    return HTMLResponse(pagina_inicial(), headers={"Cache-Control": "no-cache"})


@app.get("/privacidade", include_in_schema=False)
def privacidade() -> FileResponse:
    # Pública: a política tem de estar disponível antes do login, inclusive na tela de entrada.
    return FileResponse(WEB / "privacidade.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(WEB / "favicon.svg", media_type="image/svg+xml", headers={"Cache-Control": CACHE_ESTATICO})


app.mount("/static", StaticFiles(directory=WEB), name="static")
