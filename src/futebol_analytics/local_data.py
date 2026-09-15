"""Transformação e auditoria determinísticas das capturas locais; sem rede ou SQL."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class LocalDataset:
    championships: list[dict[str, Any]]
    teams: list[dict[str, Any]]
    matches: list[dict[str, Any]]
    report: dict[str, Any]


def positive_id(value: Any) -> bool:
    return type(value) is int and value > 0


def build_dataset(captures: list[dict[str, Any]]) -> LocalDataset:
    """Usa as últimas rodadas por origem/escopo e o catálogo anterior à coleta."""
    issues: list[dict[str, Any]] = []
    championships: dict[tuple, dict] = {}
    teams: dict[tuple, dict] = {}
    matches: dict[tuple, dict] = {}
    blocked: set[tuple] = set()
    coverage: list[dict] = []
    catalogs: list[tuple[dict, dict]] = []

    def issue(code: str, capture: dict, match_id: Any = None) -> None:
        issues.append({"codigo": code, "captura_id": str(capture["id"]), "partida_id": match_id})

    ordered = sorted(captures, key=lambda c: (c["fim_coleta"], c["gravado_em"], str(c["id"])))
    latest: dict[tuple, dict] = {}
    for capture in ordered:
        latest[(capture["origem"], capture["recurso"], capture["escopo"])] = capture
        if capture["recurso"] != "campeonatos":
            continue
        for page in capture["conteudo"].get("paginas", []):
            for item in page.get("data", []):
                if (not positive_id(item.get("id")) or str(item.get("temporada")) != capture["escopo"]):
                    issue("campeonato_invalido", capture)
                    continue
                key = (capture["origem"], item["id"], str(item["temporada"]))
                record = dict(origem=key[0], id=key[1], temporada=key[2], nome=item.get("nome"),
                              tipo=item.get("tipo"), captura_id=capture["id"])
                championships[key] = record
                catalogs.append((capture, record))

    for capture in sorted(latest.values(), key=lambda c: (c["fim_coleta"], str(c["id"]))):
        if capture["recurso"] != "rodadas":
            continue
        candidates = [(c, r) for c, r in catalogs if r["origem"] == capture["origem"]
                      and str(r["id"]) == capture["escopo"] and c["fim_coleta"] <= capture["inicio_coleta"]]
        if not candidates:
            issue("rodadas_sem_catalogo_anterior", capture)
            continue
        _, championship = candidates[-1]
        origin, cid, season = championship["origem"], championship["id"], championship["temporada"]
        rounds = capture["conteudo"]["data"]
        raw_count = 0
        for round_ in rounds:
            for match in round_.get("partidas", []):
                raw_count += 1
                mid = match.get("id")
                home, away = match.get("time_mandante"), match.get("time_visitante")
                if (not positive_id(mid) or not isinstance(home, dict) or not isinstance(away, dict)
                        or not positive_id(home.get("id")) or not positive_id(away.get("id"))
                        or home["id"] == away["id"]):
                    issue("identificacao_invalida", capture, mid)
                    continue
                for team in (home, away):
                    if not team.get("nome"):
                        issue("time_sem_nome", capture, mid)
                    teams[(origin, team["id"])] = dict(origem=origin, id=team["id"], nome=team.get("nome"),
                                                       sigla=team.get("sigla"), captura_id=capture["id"])
                kickoff = None
                raw_date = match.get("data_hora_realizacao")
                if raw_date:
                    try:
                        kickoff = datetime.fromisoformat(raw_date)
                        if kickoff.tzinfo is None:
                            raise ValueError
                    except (ValueError, TypeError):
                        issue("data_invalida", capture, mid)
                        kickoff = None
                else:
                    issue("data_ausente", capture, mid)
                scores = []
                for field in ("placar_mandante", "placar_visitante"):
                    value = match.get(field)
                    if value is not None and (type(value) is not int or value < 0):
                        issue("placar_invalido", capture, mid)
                        value = None
                    scores.append(value)
                status = match.get("status")
                if status not in ("encerrado", "aguardando", "adiado", "ao_vivo"):
                    issue("status_desconhecido", capture, mid)
                if status == "encerrado" and None in scores:
                    issue("encerrado_sem_placar", capture, mid)
                if status in ("aguardando", "adiado") and any(score is not None for score in scores):
                    issue("nao_iniciado_com_placar", capture, mid)
                if status == "encerrado" and kickoff and kickoff > capture["fim_coleta"]:
                    issue("encerrado_com_data_futura_na_coleta", capture, mid)
                number = round_.get("numero")
                if not positive_id(number):
                    issue("rodada_invalida", capture, mid)
                    number = None
                key = (origin, cid, season, mid)
                record = dict(origem=origin, campeonato_id=cid, temporada=season, id=mid, rodada=number,
                              mandante_id=home["id"], visitante_id=away["id"], status=status,
                              data_hora=kickoff, placar_mandante=scores[0], placar_visitante=scores[1],
                              captura_id=capture["id"])
                if key in blocked:
                    issue("duplicata_conflitante", capture, mid)
                elif key in matches:
                    if matches[key] == record:
                        issue("duplicata_identica", capture, mid)
                    else:
                        issue("duplicata_conflitante", capture, mid)
                        del matches[key]
                        blocked.add(key)
                else:
                    matches[key] = record
        coverage.append(dict(origem=origin, campeonato_id=cid, nome=championship["nome"], temporada=season,
                             captura_id=str(capture["id"]), coletado_em=capture["fim_coleta"].isoformat(),
                             rodadas=len(rounds), registros_recebidos=raw_count))

    for entry in coverage:
        selected = [m for m in matches.values() if (m["origem"], m["campeonato_id"], m["temporada"]) ==
                    (entry["origem"], entry["campeonato_id"], entry["temporada"])]
        entry.update(partidas_normalizadas=len(selected), status=dict(Counter(m["status"] for m in selected)),
                     encerradas_com_placar=sum(m["status"] == "encerrado" and m["placar_mandante"] is not None
                                             and m["placar_visitante"] is not None for m in selected))
    covered = {(c["origem"], c["campeonato_id"], c["temporada"]) for c in coverage}
    uncovered = [dict(id=c["id"], nome=c["nome"], temporada=c["temporada"])
                 for key, c in championships.items() if key not in covered]
    report = dict(versao="normalizacao_v1", campeonatos=len(championships), times=len(teams), partidas=len(matches),
                  cobertura=coverage, campeonatos_sem_rodadas=uncovered,
                  ocorrencias=dict(Counter(i["codigo"] for i in issues)), detalhes=issues,
                  limite="Cobertura das capturas locais; não comprova calendário completo nem valida a fonte externamente.")
    return LocalDataset(list(championships.values()), list(teams.values()), list(matches.values()), report)
