"""Formatos de entrada e saída da API."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Status


class LeadCriar(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    nicho: str = Field(min_length=1, max_length=80)
    cidade: str = ""
    whatsapp: str = Field(min_length=8, max_length=20)
    instagram: str = ""
    site: str = ""
    avaliacao: float | None = Field(default=None, ge=0, le=5)
    num_avaliacoes: int = Field(default=0, ge=0)
    vende_em_app: bool = False
    observacao: str = ""


class LeadAtualizar(BaseModel):
    nome: str | None = None
    nicho: str | None = None
    cidade: str | None = None
    instagram: str | None = None
    site: str | None = None
    avaliacao: float | None = Field(default=None, ge=0, le=5)
    num_avaliacoes: int | None = Field(default=None, ge=0)
    vende_em_app: bool | None = None
    observacao: str | None = None


class LeadSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    nicho: str
    cidade: str
    whatsapp: str
    instagram: str
    site: str
    avaliacao: float | None
    num_avaliacoes: int
    vende_em_app: bool
    nota: int
    status: Status
    abordado_em: date | None
    followup_em: date | None
    followups_enviados: int
    motivo_perda: str
    observacao: str
    criado_em: datetime


class NotaSaida(BaseModel):
    lead_id: int
    nota: int
    detalhes: dict[str, int]


class MudarStatus(BaseModel):
    status: Status
    motivo: str = Field(default="", description="Objeção ou motivo (ex.: 'já tem iFood', 'vai falar com o sócio')")
    followup_em: date | None = Field(default=None, description="Se vazio, a API calcula pela etapa")


class InteracaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    descricao: str
    criado_em: datetime


class Funil(BaseModel):
    total: int
    por_status: dict[str, int]
    abordados: int
    responderam: int
    fecharam: int
    taxa_resposta: float
    taxa_fechamento: float


class ResultadoImportacao(BaseModel):
    importados: int
    repetidos: int
    invalidos: int
