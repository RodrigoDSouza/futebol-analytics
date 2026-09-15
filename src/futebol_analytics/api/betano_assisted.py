"""Navegação assistida em contexto descartável, com captura explícita pelo usuário."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright

BUTTON = """() => {
  if (document.getElementById('futebol-capturar')) return;
  const button = document.createElement('button');
  button.id = 'futebol-capturar';
  button.textContent = 'Salvar página para análise';
  button.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:2147483647;padding:14px;background:#123;color:white;border:2px solid white;border-radius:8px;cursor:pointer';
  button.onclick = async () => {
    button.disabled = true;
    try {
      button.textContent = await window.futebolSalvar();
    } catch (_) { button.textContent = 'Não foi possível salvar'; }
    button.disabled = false;
  };
  document.body.appendChild(button);
}"""


def main() -> int:
    parser = argparse.ArgumentParser(description='Navega??o p?blica assistida da Betano')
    parser.add_argument('--url', default='https://www.betano.bet.br/')
    args = parser.parse_args()
    target = urlsplit(args.url)
    if target.scheme != 'https' or target.hostname not in ('betano.bet.br', 'www.betano.bet.br') or target.username or target.password:
        parser.error('Use uma URL HTTPS p?blica da Betano.')
    folder = Path('.venv/betano_assistido')
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, timeout=30000)
        context = browser.new_context(locale='pt-BR', viewport={'width': 1440, 'height': 960})

        def save(source):
            page = source['page']
            if urlsplit(page.url).hostname not in ('betano.bet.br', 'www.betano.bet.br'):
                return 'Abra uma página pública da Betano'
            stamp = datetime.now(timezone.utc)
            prefix = folder / stamp.strftime('%Y%m%dT%H%M%S%fZ')
            # Somente texto renderizado e viewport; não coleta cookies, storage ou HTML.
            text = page.locator('body').inner_text(timeout=10000)
            prefix.with_suffix('.txt').write_text(text, encoding='utf-8')
            page.screenshot(path=str(prefix.with_suffix('.png')), timeout=10000)
            prefix.with_suffix('.json').write_text(json.dumps({
                'observado_em': stamp.isoformat(),
                'pagina': urlsplit(page.url)._replace(query='', fragment='').geturl(),
                'status': 'captura_visual_nao_validada', 'odds_extraidas': False,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Captura salva: {prefix}', flush=True)
            return 'Página salva — pode avisar no chat'

        pending = []

        def enqueue(source):
            pending.append(source)
            return 'Captura solicitada ? aguarde confirma??o'

        context.expose_binding('futebolSalvar', enqueue)
        page = context.new_page()
        try:
            try:
                response = page.goto(args.url, wait_until='domcontentloaded', timeout=45000)
                print(f'HTTP inicial: {response.status if response else "sem resposta"}', flush=True)
            except Error:
                print('A navegação inicial não terminou; verifique a janela.', flush=True)
            print('Janela disponível por 10 minutos. Abra o mercado desejado e clique em Salvar página para análise. Use somente páginas públicas.', flush=True)
            deadline = time.monotonic() + 600
            while context.pages and time.monotonic() < deadline:
                while pending:
                    source = pending.pop(0)
                    try:
                        message = save(source)
                        source['page'].locator('#futebol-capturar').evaluate('(button, message) => button.textContent = message', message)
                    except (Error, OSError):
                        print('Falha ao gravar captura; tente novamente.', flush=True)
                for current in context.pages:
                    try:
                        if urlsplit(current.url).hostname in ('betano.bet.br', 'www.betano.bet.br'):
                            current.evaluate(BUTTON)
                    except Error:
                        pass  # Pode estar navegando ou fechando.
                try:
                    context.pages[0].wait_for_timeout(1000)
                except (Error, IndexError):
                    break
        finally:
            browser.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
