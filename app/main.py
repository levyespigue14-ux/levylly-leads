"""Levylly Leads: API de prospecção para estúdios que vendem sites a negócios locais."""
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.database import Base, engine, get_db
from app.models import Lead, Status, TipoInteracao
from app.schemas import (Funil, InteracaoSaida, LeadAtualizar, LeadCriar, LeadSaida, MudarStatus,
                         NotaSaida, ResultadoImportacao)
from app.scoring import calcular_nota


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Levylly Leads",
    version="0.1.0",
    description="Encontra, prioriza e acompanha leads de negócios locais: nota automática, "
                "CRM com follow-ups e funil de prospecção.",
    lifespan=lifespan,
)

DB = Annotated[Session, Depends(get_db)]


def _lead(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead não encontrado.")
    return lead


def _negocio(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except services.ErroDeNegocio as e:
        raise HTTPException(409, str(e)) from e


@app.get("/health", tags=["sistema"])
def health():
    return {"status": "ok"}


# ------------------------------- leads -------------------------------------
@app.post("/leads", response_model=LeadSaida, status_code=201, tags=["leads"])
def criar_lead(dados: LeadCriar, db: DB):
    return _negocio(services.criar_lead, db, dados.model_dump())


@app.get("/leads", response_model=list[LeadSaida], tags=["leads"])
def listar_leads(
    db: DB,
    nicho: str | None = None,
    cidade: str | None = None,
    status: Status | None = None,
    nota_minima: int = Query(0, ge=0, le=100),
    limite: int = Query(50, ge=1, le=500),
):
    q = select(Lead).where(Lead.nota >= nota_minima)
    if nicho:
        q = q.where(Lead.nicho.ilike(f"%{nicho}%"))
    if cidade:
        q = q.where(Lead.cidade.ilike(f"%{cidade}%"))
    if status:
        q = q.where(Lead.status == status)
    return list(db.scalars(q.order_by(Lead.nota.desc(), Lead.id).limit(limite)))


@app.get("/leads/proximos", response_model=list[LeadSaida], tags=["prospecção"],
         summary="Os melhores leads novos para abordar hoje (maior nota primeiro)")
def proximos(db: DB, nicho: str | None = None, cidade: str | None = None,
             limite: int = Query(25, ge=1, le=100)):
    return services.proximos_para_abordar(db, nicho, cidade, limite)


@app.get("/leads/{lead_id}", response_model=LeadSaida, tags=["leads"])
def ver_lead(lead_id: int, db: DB):
    return _lead(db, lead_id)


@app.patch("/leads/{lead_id}", response_model=LeadSaida, tags=["leads"])
def atualizar_lead(lead_id: int, dados: LeadAtualizar, db: DB):
    lead = _lead(db, lead_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(lead, campo, valor)
    services.atualizar_nota(lead)
    db.commit()
    db.refresh(lead)
    return lead


@app.delete("/leads/{lead_id}", status_code=204, tags=["leads"])
def apagar_lead(lead_id: int, db: DB):
    db.delete(_lead(db, lead_id))
    db.commit()


@app.get("/leads/{lead_id}/nota", response_model=NotaSaida, tags=["leads"],
         summary="Explica a nota do lead, critério por critério")
def explicar_nota(lead_id: int, db: DB):
    lead = _lead(db, lead_id)
    n = calcular_nota(avaliacao=lead.avaliacao, num_avaliacoes=lead.num_avaliacoes, site=lead.site,
                      whatsapp=lead.whatsapp, instagram=lead.instagram)
    return NotaSaida(lead_id=lead.id, nota=n.total, detalhes=n.detalhes)


@app.get("/leads/{lead_id}/historico", response_model=list[InteracaoSaida], tags=["leads"])
def historico(lead_id: int, db: DB):
    return _lead(db, lead_id).interacoes


# ----------------------------- prospecção ----------------------------------
@app.post("/leads/{lead_id}/abordagem", response_model=LeadSaida, tags=["prospecção"],
          summary="Registra que a primeira mensagem foi enviada e agenda o follow-up")
def registrar_abordagem(lead_id: int, db: DB):
    return _negocio(services.registrar_envio, db, _lead(db, lead_id), TipoInteracao.ABORDAGEM)


@app.post("/leads/{lead_id}/followup", response_model=LeadSaida, tags=["prospecção"],
          summary="Registra que um follow-up foi enviado e agenda o próximo (ou encerra)")
def registrar_followup(lead_id: int, db: DB):
    return _negocio(services.registrar_envio, db, _lead(db, lead_id), TipoInteracao.FOLLOWUP)


@app.post("/leads/{lead_id}/status", response_model=LeadSaida, tags=["prospecção"],
          summary="Muda a etapa do lead (respondeu, sócio, perdido...) e guarda a objeção")
def mudar_status(lead_id: int, dados: MudarStatus, db: DB):
    return services.mudar_status(db, _lead(db, lead_id), dados.status, dados.motivo, dados.followup_em)


@app.get("/followups", response_model=list[LeadSaida], tags=["prospecção"],
         summary="Follow-ups vencidos até a data (padrão: hoje), respeitando o limite diário")
def followups(db: DB, data: date | None = None, limite: int | None = Query(None, ge=1, le=100)):
    return services.followups_do_dia(db, data, limite)


# ------------------------------- métricas ----------------------------------
@app.get("/funil", response_model=Funil, tags=["métricas"])
def ver_funil(db: DB, nicho: str | None = None):
    return services.funil(db, nicho)


@app.get("/funil/objecoes", tags=["métricas"], summary="Objeções mais comuns (o que travou as vendas)")
def ver_objecoes(db: DB) -> dict[str, int]:
    return services.objecoes(db)


# ------------------------------- importação --------------------------------
@app.post("/importar/csv", response_model=ResultadoImportacao, tags=["importação"],
          summary="Importa uma planilha CSV de leads (separador ; ou ,), ignorando telefones repetidos")
async def importar_csv(db: DB, arquivo: UploadFile = File(...)):
    return services.importar_csv(db, await arquivo.read())
