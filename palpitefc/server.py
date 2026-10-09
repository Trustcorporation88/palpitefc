"""Site do PalpiteFC. A conta roda aqui; o navegador só mostra."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from palpitefc.servico import painel

WEB = Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="PalpiteFC")


@app.on_event("startup")
def preparar() -> None:
    painel()


@app.get("/api/inicio")
def inicio() -> dict:
    return painel().inicio()


@app.get("/api/times")
def times() -> dict:
    return {"times": painel().times()}


@app.get("/api/time/{time}")
def do_time(time: str) -> dict:
    try:
        return painel().do_time(time)
    except KeyError:
        raise HTTPException(status_code=404, detail="Time fora do Brasileirão 2026") from None


@app.get("/api/simular")
def simular(casa: str, fora: str) -> dict:
    try:
        return painel().simular(casa, fora)
    except KeyError:
        raise HTTPException(status_code=400, detail="Escolha dois times diferentes do campeonato") from None


@app.get("/api/forca")
def forca() -> dict:
    return {"times": painel().forca()}


@app.get("/")
def raiz() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
