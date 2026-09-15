"""Diagnóstico limitado da página pública; nenhum extrator de odds validado ainda."""

from datetime import datetime, timezone
from typing import Any

URL = "https://www.betano.bet.br/sport/futebol/"


def diagnose() -> dict[str, Any]:
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        raise ValueError("Instale o extra browser e execute python -m playwright install chromium.") from None
    result: dict[str, Any] = {
        "url": URL, "consultado_em": datetime.now(timezone.utc).isoformat(),
        "status": "erro_navegador", "http_status": None, "odds": [],
        "coleta_odds_validada": False,
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, timeout=30000)
            try:
                page = browser.new_page(locale="pt-BR")
                response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
                status = response.status if response else None
                result["http_status"] = status
                if status in (401, 403, 429):
                    result.update(status="acesso_recusado", motivo="Página recusou o acesso; nenhuma repetição ou contorno realizado.")
                elif status is None or status >= 400:
                    result.update(status="erro_http", motivo="Não foi possível carregar a página pública.")
                else:
                    result.update(status="extracao_nao_validada", motivo="Página respondeu, mas o formato das odds ainda exige validação. HTTP 200 não comprova coleta.")
            finally:
                browser.close()
    except Error:
        # Evita persistir detalhes do ambiente e não mascara falha como lista vazia válida.
        result["motivo"] = "Falha ou timeout do navegador. Verifique a instalação do Chromium e a conexão."
    result["finalizado_em"] = datetime.now(timezone.utc).isoformat()
    return result
