"""Triagem experimental de odds explícitas, sem executar apostas ou prometer lucro."""

from datetime import datetime, timedelta, timezone
from collections import Counter
import math
import unicodedata
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MARKETS = {"mandante", "empate", "visitante", "over_0.5", "over_1.5", "over_2.5", "over_3.5", "ambas_marcam"}


def timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Data deve estar em ISO 8601 com fuso horário.")
    return value


def name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Nome do time ausente.")
    return " ".join(unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().split())


def fresh(value: Any, now: datetime, maximum: timedelta, label: str) -> None:
    age = now - timestamp(value)
    if age < timedelta(0) or age > maximum:
        raise ValueError(f"{label}: data futura ou desatualizada.")


def evaluate(quotes: list[dict[str, Any]], predict: Callable[[int, int, str], dict[str, Any]],
             *, now: datetime | None = None) -> dict[str, Any]:
    """predict recebe ID da partida, campeonato e temporada. Uma observação por mercado."""
    now = timestamp(now or datetime.now(timezone.utc))
    try:
        local_zone = ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        raise ValueError("Instale tzdata para interpretar America/Sao_Paulo no Windows.") from None
    if not isinstance(quotes, list) or len(quotes) > 1000:
        raise ValueError("Informe uma lista JSON com no máximo 1000 cotações.")
    candidates, rejected = [], []
    cache: dict[tuple, dict[str, Any]] = {}
    # Duplicatas são ambíguas, inclusive quando têm odds diferentes. Rejeita todas.
    keys = []
    for quote in quotes:
        if not isinstance(quote, dict):
            raise ValueError("Cada cotação deve ser um objeto JSON.")
        keys.append(tuple(str(quote.get(k)) for k in ("partida_id", "campeonato_id", "temporada", "mercado")))
    duplicates = {key for key, count in Counter(keys).items() if count > 1}
    for index, quote in enumerate(quotes):
        try:
            if keys[index] in duplicates:
                raise ValueError("Cotação duplicada para a mesma partida e mercado.")
            for field in ("partida_id", "campeonato_id"):
                if type(quote.get(field)) is not int or quote[field] <= 0:
                    raise ValueError(f"{field} deve ser um inteiro positivo da base local.")
            if not isinstance(quote.get("temporada"), str) or not quote["temporada"].isdigit():
                raise ValueError("Temporada inválida.")
            market = quote.get("mercado")
            if market not in MARKETS or quote.get("periodo") != "tempo_regulamentar":
                raise ValueError("Mercado/período não suportado: use resultado, gols ou ambas marcam no tempo regulamentar.")
            odd = quote.get("odd")
            if type(odd) not in (int, float) or not math.isfinite(odd) or not 1.45 <= odd <= 1.55:
                raise ValueError("Odd fora da faixa 1,45 a 1,55 ou inválida.")
            url = urlsplit(quote.get("url", ""))
            if url.scheme != "https" or url.hostname not in ("betano.bet.br", "www.betano.bet.br") or url.username or url.password:
                raise ValueError("Informe a URL HTTPS pública da Betano.")
            fresh(quote.get("observado_em"), now, timedelta(minutes=15), "Odd")
            kickoff = timestamp(quote.get("data_hora"))
            if kickoff <= now or kickoff.astimezone(local_zone).date() != now.astimezone(local_zone).date():
                raise ValueError("A partida precisa ocorrer hoje em São Paulo e ainda não ter começado.")
            key = (quote["partida_id"], quote["campeonato_id"], quote["temporada"])
            if key not in cache:
                cache[key] = predict(*key)
            report = cache[key]
            target = report["partida"]
            if (target["id"], target["campeonato_id"], target["temporada"]) != key:
                raise ValueError("Identificação da previsão diverge da cotação.")
            if any(name(quote.get(side)) != name(target.get(side)) for side in ("mandante", "visitante")) or timestamp(target["data_hora"]) != kickoff:
                raise ValueError("Nomes, mando ou horário não correspondem exatamente à base local.")
            fresh(report["calculado_em"], now, timedelta(minutes=15), "Previsão")
            fresh(report["agenda_observada_em"], now, timedelta(hours=24), "Agenda")
            fresh(report["amostra"]["ultima_coleta_utilizada"], now, timedelta(hours=24), "Resultados")
            probability = report["probabilidades"][market]
            if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 < probability < 1:
                raise ValueError("Probabilidade inválida ou extrema; requer revisão.")
            ev = probability * odd - 1
            if ev <= 0:
                raise ValueError("Sem vantagem estimada pelo modelo nessa odd.")
            candidates.append({
                "cotacao": quote, "probabilidade_modelo": probability,
                "probabilidade_equilibrio": 1 / odd, "odd_justa_modelo": 1 / probability,
                "valor_esperado_por_real_modelo": ev, "previsao": report,
            })
        except (ValueError, KeyError, TypeError) as error:
            reason = str(error) if isinstance(error, ValueError) else "Dados obrigatórios ausentes ou inválidos."
            rejected.append({"indice": index, "motivo": reason})
    candidates.sort(key=lambda item: (-item["valor_esperado_por_real_modelo"], item["cotacao"]["partida_id"], item["cotacao"]["mercado"]))
    selected, games = [], set()
    for item in candidates:
        quote = item["cotacao"]
        key = (quote["campeonato_id"], quote["temporada"], quote["partida_id"])
        if key not in games and len(selected) < 3:
            selected.append(item)
            games.add(key)
    return {
        "status": "simulacao", "calculado_em": now.isoformat(), "entrada": "cotacoes_informadas_nao_verificadas_online",
        "criterios": {"odd_min": 1.45, "odd_max": 1.55, "max_jogos": 3, "idade_odd_minutos": 15,
                      "idade_base_horas": 24, "fuso": "America/Sao_Paulo"},
        "candidatos_experimentais": selected, "elegiveis_antes_limite": len(candidates), "rejeitadas": rejected,
        "limitacoes": ["Poisson v1 sem calibração ou backtesting: vantagem calculada não é vantagem comprovada.",
                       "Odds informadas precisam ser conferidas na Betano; esta análise não as coleta.",
                       "Atualidade da última captura não garante cobertura completa dos resultados.",
                       "Nenhuma aposta é executada. Não há plano de alavancagem nem garantia de retorno."],
    }
