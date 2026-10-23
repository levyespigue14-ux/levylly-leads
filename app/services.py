"""Regras do negócio: nota, etapas do funil, follow-ups e importação de planilha."""
import csv
import io
import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Interacao, Lead, Status, TipoInteracao
from app.scoring import calcular_nota

# Status em que o lead ainda espera uma mensagem nossa no dia marcado
STATUS_COM_FOLLOWUP = (Status.ABORDADO, Status.FOLLOWUP, Status.SOCIO)
# Status que contam como "o cliente respondeu"
STATUS_RESPONDEU = (Status.RESPONDEU, Status.SOCIO, Status.INTERESSADO, Status.PROPOSTA, Status.FECHADO)


class ErroDeNegocio(ValueError):
    pass


def normalizar_telefone(numero: str) -> str:
    """'(11) 99999-0000' -> '5511999990000'. Devolve '' se não parecer telefone brasileiro."""
    d = re.sub(r"\D", "", numero or "")
    if len(d) in (10, 11):
        d = "55" + d
    return d if len(d) in (12, 13) and d.startswith("55") else ""


def dia_util(d: date) -> date:
    """Não marca follow-up para domingo."""
    return d + timedelta(days=1) if d.weekday() == 6 else d


def atualizar_nota(lead: Lead) -> None:
    lead.nota = calcular_nota(
        avaliacao=lead.avaliacao,
        num_avaliacoes=lead.num_avaliacoes,
        site=lead.site,
        whatsapp=lead.whatsapp,
        instagram=lead.instagram,
    ).total


def registrar(db: Session, lead: Lead, tipo: TipoInteracao, descricao: str = "") -> None:
    db.add(Interacao(lead=lead, tipo=tipo, descricao=descricao))


def criar_lead(db: Session, dados: dict) -> Lead:
    tel = normalizar_telefone(dados.get("whatsapp", ""))
    if not tel:
        raise ErroDeNegocio("Telefone inválido.")
    if db.scalar(select(Lead).where(Lead.whatsapp == tel)):
        raise ErroDeNegocio("Já existe um lead com esse WhatsApp.")
    lead = Lead(**{**dados, "whatsapp": tel})
    atualizar_nota(lead)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def registrar_envio(db: Session, lead: Lead, tipo: TipoInteracao, hoje: date | None = None) -> Lead:
    """Marca que a abordagem ou um follow-up foi enviado e agenda o próximo passo."""
    cfg, hoje = get_settings(), hoje or date.today()
    if tipo == TipoInteracao.ABORDAGEM:
        if lead.status != Status.NOVO:
            raise ErroDeNegocio("Esse lead já foi abordado.")
        lead.status, lead.abordado_em = Status.ABORDADO, hoje
        lead.followup_em = dia_util(hoje + timedelta(days=cfg.dias_primeiro_followup))
    elif tipo == TipoInteracao.FOLLOWUP:
        if lead.status not in STATUS_COM_FOLLOWUP:
            raise ErroDeNegocio(f"Lead em '{lead.status}' não tem follow-up pendente.")
        lead.followups_enviados += 1
        if lead.status == Status.SOCIO:
            # 1º: "conseguiu falar com o sócio?"  2º: última mensagem
            lead.followup_em = (dia_util(hoje + timedelta(days=3)) if lead.followups_enviados == 1 else None)
        else:
            lead.status = Status.FOLLOWUP
            lead.followup_em = (dia_util(hoje + timedelta(days=cfg.dias_segundo_followup))
                                if lead.followups_enviados < 2 else None)
    else:
        raise ErroDeNegocio("Envio deve ser 'abordagem' ou 'followup'.")
    registrar(db, lead, tipo)
    db.commit()
    db.refresh(lead)
    return lead


def mudar_status(db: Session, lead: Lead, novo: Status, motivo: str = "",
                 followup_em: date | None = None, hoje: date | None = None) -> Lead:
    cfg, hoje = get_settings(), hoje or date.today()
    anterior = lead.status
    lead.status = novo
    if novo == Status.SOCIO:
        lead.followups_enviados = 0
        lead.followup_em = followup_em or dia_util(hoje + timedelta(days=cfg.dias_socio))
    elif novo == Status.PERDIDO:
        lead.motivo_perda, lead.followup_em = motivo, None
    elif novo == Status.FECHADO:
        lead.followup_em = None
    else:
        lead.followup_em = followup_em
    if motivo and novo != Status.PERDIDO:
        registrar(db, lead, TipoInteracao.OBJECAO, motivo)
    registrar(db, lead, TipoInteracao.STATUS, f"{anterior} -> {novo}" + (f" ({motivo})" if motivo else ""))
    db.commit()
    db.refresh(lead)
    return lead


def followups_do_dia(db: Session, hoje: date | None = None, limite: int | None = None) -> list[Lead]:
    hoje = hoje or date.today()
    q = (select(Lead)
         .where(Lead.status.in_([s.value for s in STATUS_COM_FOLLOWUP]),
                Lead.followup_em.is_not(None), Lead.followup_em <= hoje)
         .order_by(Lead.followup_em, Lead.nota.desc()))
    return list(db.scalars(q.limit(limite or get_settings().limite_diario)))


def proximos_para_abordar(db: Session, nicho: str | None, cidade: str | None, limite: int) -> list[Lead]:
    q = select(Lead).where(Lead.status == Status.NOVO)
    if nicho:
        q = q.where(Lead.nicho.ilike(f"%{nicho}%"))
    if cidade:
        q = q.where(Lead.cidade.ilike(f"%{cidade}%"))
    return list(db.scalars(q.order_by(Lead.nota.desc(), Lead.id).limit(limite)))


def funil(db: Session, nicho: str | None = None) -> dict:
    q = select(Lead.status, func.count()).group_by(Lead.status)
    if nicho:
        q = q.where(Lead.nicho.ilike(f"%{nicho}%"))
    por_status = {s.value: 0 for s in Status} | {s: n for s, n in db.execute(q).all()}
    total = sum(por_status.values())
    abordados = total - por_status[Status.NOVO]
    responderam = sum(por_status[s] for s in STATUS_RESPONDEU) + _perdidos_que_responderam(db, nicho)
    fecharam = por_status[Status.FECHADO]
    return {
        "total": total,
        "por_status": por_status,
        "abordados": abordados,
        "responderam": responderam,
        "fecharam": fecharam,
        "taxa_resposta": round(responderam / abordados, 3) if abordados else 0.0,
        "taxa_fechamento": round(fecharam / abordados, 3) if abordados else 0.0,
    }


def _perdidos_que_responderam(db: Session, nicho: str | None) -> int:
    """Quem disse 'não quero' respondeu: perdido com motivo conta como resposta."""
    q = select(func.count()).select_from(Lead).where(Lead.status == Status.PERDIDO, Lead.motivo_perda != "")
    if nicho:
        q = q.where(Lead.nicho.ilike(f"%{nicho}%"))
    return db.scalar(q) or 0


def objecoes(db: Session) -> dict[str, int]:
    """Quantas vezes cada objeção apareceu (o dado que mostra o que melhorar na abordagem)."""
    rows = db.execute(select(Interacao.descricao, func.count())
                      .where(Interacao.tipo == TipoInteracao.OBJECAO)
                      .group_by(Interacao.descricao).order_by(func.count().desc())).all()
    perdas = db.execute(select(Lead.motivo_perda, func.count())
                        .where(Lead.status == Status.PERDIDO, Lead.motivo_perda != "")
                        .group_by(Lead.motivo_perda)).all()
    out: dict[str, int] = {}
    for motivo, n in [*rows, *perdas]:
        chave = motivo.strip().lower()
        out[chave] = out.get(chave, 0) + n
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------------------
# Importação de planilha (mesmo formato da planilha da assistente Marin)
# nome;nicho;cidade;whatsapp;instagram;avaliacao;status;abordado_em;followup_em;observacao
# Colunas extras aceitas: site; num_avaliacoes
# ---------------------------------------------------------------------------
MAPA_STATUS = {"pulado": Status.PERDIDO, "sem_interesse": Status.PERDIDO, "socio_ultima": Status.SOCIO,
               "conferir": Status.NOVO}


def _data(v: str) -> date | None:
    try:
        return date.fromisoformat(v.strip()) if v and v.strip() else None
    except ValueError:
        return None


def _float(v: str) -> float | None:
    try:
        return float(v.replace(",", ".")) if v and v.strip() else None
    except ValueError:
        return None


def importar_csv(db: Session, conteudo: bytes) -> dict:
    texto = conteudo.decode("utf-8-sig", errors="replace")
    sep = ";" if texto[:2048].count(";") >= texto[:2048].count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=sep)
    existentes = set(db.scalars(select(Lead.whatsapp)))
    importados = repetidos = invalidos = 0
    for linha in leitor:
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}
        tel = normalizar_telefone(linha.get("whatsapp", ""))
        if not tel or not linha.get("nome"):
            invalidos += 1
            continue
        if tel in existentes:
            repetidos += 1
            continue
        bruto = linha.get("status") or "novo"
        status = MAPA_STATUS.get(bruto) or (Status(bruto) if bruto in Status._value2member_map_ else Status.NOVO)
        lead = Lead(
            nome=linha["nome"], nicho=linha.get("nicho") or "outros", cidade=linha.get("cidade", ""),
            whatsapp=tel, instagram=linha.get("instagram", ""), site=linha.get("site", ""),
            avaliacao=_float(linha.get("avaliacao", "")),
            num_avaliacoes=int(linha["num_avaliacoes"]) if linha.get("num_avaliacoes", "").isdigit() else 0,
            status=status, abordado_em=_data(linha.get("abordado_em", "")),
            followup_em=_data(linha.get("followup_em", "")), observacao=linha.get("observacao", ""),
            motivo_perda="importado como sem interesse" if bruto == "sem_interesse" else "",
        )
        atualizar_nota(lead)
        db.add(lead)
        existentes.add(tel)
        importados += 1
    db.commit()
    return {"importados": importados, "repetidos": repetidos, "invalidos": invalidos}
