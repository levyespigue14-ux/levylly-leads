"""Tabelas do banco: leads e o histórico de interações com cada um."""
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Status(StrEnum):
    NOVO = "novo"
    ABORDADO = "abordado"
    FOLLOWUP = "followup"
    RESPONDEU = "respondeu"
    SOCIO = "socio"              # "vou conversar com o sócio"
    INTERESSADO = "interessado"
    PROPOSTA = "proposta"
    FECHADO = "fechado"
    PERDIDO = "perdido"


class TipoInteracao(StrEnum):
    ABORDAGEM = "abordagem"
    FOLLOWUP = "followup"
    RESPOSTA = "resposta"
    OBJECAO = "objecao"
    STATUS = "status"
    NOTA = "nota"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), index=True)
    nicho: Mapped[str] = mapped_column(String(80), index=True)
    cidade: Mapped[str] = mapped_column(String(120), index=True, default="")
    whatsapp: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    instagram: Mapped[str] = mapped_column(String(120), default="")
    site: Mapped[str] = mapped_column(String(300), default="")
    avaliacao: Mapped[float | None] = mapped_column(Float, nullable=True)
    num_avaliacoes: Mapped[int] = mapped_column(Integer, default=0)
    vende_em_app: Mapped[bool] = mapped_column(default=False)   # iFood, 99Food etc.

    nota: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(20), default=Status.NOVO, index=True)
    abordado_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    followup_em: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    followups_enviados: Mapped[int] = mapped_column(Integer, default=0)
    motivo_perda: Mapped[str] = mapped_column(String(120), default="")
    observacao: Mapped[str] = mapped_column(Text, default="")

    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    interacoes: Mapped[list["Interacao"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Interacao.id"
    )


class Interacao(Base):
    __tablename__ = "interacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    descricao: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lead: Mapped[Lead] = relationship(back_populates="interacoes")
