"""Contas do PalpiteFC: login por e-mail e senha no Supabase, e o aceite dos termos.

O servidor não guarda senha nem sessão. Ele pergunta ao Supabase quem é o
dono do token (/auth/v1/user) e lê o aceite com o próprio token da pessoa:
a regra de segurança do banco (RLS) decide o que cada um vê. Só precisa da
URL e da chave pública (publishable), que vão para o navegador de qualquer
forma. Sem SUPABASE_URL no ambiente, as rotas da API respondem 503: o site
não abre sem login por engano.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# Quando o texto dos termos mudar, suba a versão: quem aceitou a antiga aceita de novo.
VERSAO_DO_TERMO = "1.0"
TEMPO_LIMITE = 8
# Consultar o Supabase a cada chamada da API seria lento; a sessão válida vale 60 s no servidor.
VALIDADE_DO_CACHE = 60
_cache: dict[str, tuple[float, bool]] = {}


class ContaIndisponivel(Exception):
    """O Supabase não respondeu ou a configuração falta."""


def configurado() -> bool:
    return bool(os.environ.get("SUPABASE_URL", "").strip() and os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip())


def _url(caminho: str) -> str:
    base = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not base:
        raise ContaIndisponivel("SUPABASE_URL não configurada")
    return f"{base}{caminho}"


def _chamar(caminho: str, token: str | None = None) -> dict | list | None:
    chave = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if not chave:
        raise ContaIndisponivel("SUPABASE_PUBLISHABLE_KEY não configurada")
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {token or chave}"}
    pedido = urllib.request.Request(_url(caminho), headers=cabecalhos)
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        if erro.code in (401, 403):
            return None
        raise ContaIndisponivel(f"HTTP {erro.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise ContaIndisponivel("Supabase fora do ar") from None


def _chave(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def pode_ver(token: str) -> bool:
    """Token válido e termo aceito na versão atual. O resultado vale 60 s no servidor."""
    chave = _chave(token)
    agora = time.monotonic()
    if chave in _cache and _cache[chave][0] > agora:
        return _cache[chave][1]
    usuario = _chamar("/auth/v1/user", token)
    liberado = bool(isinstance(usuario, dict) and usuario.get("id") and aceitou_o_termo(token, usuario["id"]))
    if liberado:
        # Só o "sim" fica guardado: quem acabou de aceitar não espera o cache.
        _cache[chave] = (agora + VALIDADE_DO_CACHE, True)
    return liberado


def aceitou_o_termo(token: str, usuario_id: str) -> bool:
    filtro = urllib.parse.urlencode({"user_id": f"eq.{usuario_id}", "versao": f"eq.{VERSAO_DO_TERMO}", "select": "versao"})
    linhas = _chamar(f"/rest/v1/aceites_termo?{filtro}", token)
    return bool(linhas)


def sair(token: str) -> None:
    _cache.pop(_chave(token), None)


def usuario_de(token: str) -> dict | None:
    """Quem é o dono do token, sem cache: usado só nas rotas de administrador."""
    usuario = _chamar("/auth/v1/user", token)
    return usuario if isinstance(usuario, dict) and usuario.get("id") else None


def eh_admin(usuario: dict | None) -> bool:
    admin = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    return bool(admin and usuario and str(usuario.get("email", "")).lower() == admin)


def criar_conta(email: str, senha: str) -> str:
    """Cria a conta já confirmada, sem e-mail. Devolve "criada" ou o motivo da recusa.

    Usa a chave service_role, que só existe no servidor. Ela não aparece em
    nenhuma resposta nem em log.
    """
    chave = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not chave:
        raise ContaIndisponivel("SUPABASE_SERVICE_ROLE_KEY não configurada")
    corpo = json.dumps({"email": email, "password": senha, "email_confirm": True}).encode("utf-8")
    pedido = urllib.request.Request(
        _url("/auth/v1/admin/users"),
        data=corpo,
        method="POST",
        headers={"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE):
            return "criada"
    except urllib.error.HTTPError as erro:
        try:
            motivo = json.loads(erro.read().decode("utf-8")).get("error_code", "")
        except (ValueError, AttributeError):
            motivo = ""
        if erro.code in (400, 409, 422) and motivo in ("email_exists", "user_already_exists", "weak_password", "validation_failed"):
            return motivo
        raise ContaIndisponivel(f"HTTP {erro.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ContaIndisponivel("Supabase fora do ar") from None

