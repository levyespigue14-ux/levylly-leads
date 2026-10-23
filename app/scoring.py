"""Nota do lead (0 a 100): quanto maior, maior a chance de virar cliente.

A ideia é abordar primeiro quem tem movimento (boas avaliações, muitas pessoas avaliando),
ainda não tem site próprio e tem canais para conversar (WhatsApp e Instagram).
Cada critério devolve seus pontos separados, para dar para explicar a nota.
"""
import math
import re
from dataclasses import dataclass

# Domínios que NÃO contam como site próprio (rede social, cardápio de app, agregador de links)
NAO_E_SITE = (
    "instagram.com", "facebook.com", "ifood.com.br", "linktr.ee", "wa.me", "whatsapp.com",
    "cardapioweb.com", "goomer", "anota.ai", "tiny.cc", "bit.ly",
)

PESOS = {"avaliacao": 30, "popularidade": 25, "sem_site": 20, "whatsapp": 15, "instagram": 10}


@dataclass
class Nota:
    total: int
    detalhes: dict[str, int]


def tem_site_proprio(site: str | None) -> bool:
    s = (site or "").strip().lower()
    return bool(s) and not any(d in s for d in NAO_E_SITE)


def eh_celular(telefone: str | None) -> bool:
    """Celular brasileiro: DDD + 9 dígitos começando com 9 (fixo não tem WhatsApp, em geral)."""
    d = re.sub(r"\D", "", telefone or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    return len(d) == 11 and d[2] == "9"


def calcular_nota(
    *,
    avaliacao: float | None,
    num_avaliacoes: int,
    site: str | None,
    whatsapp: str | None,
    instagram: str | None,
) -> Nota:
    d: dict[str, int] = {}

    # Nota do Google: abaixo de 3,5 não soma; 5,0 soma tudo.
    if avaliacao is not None:
        d["avaliacao"] = round(max(0.0, min(1.0, (avaliacao - 3.5) / 1.5)) * PESOS["avaliacao"])
    else:
        d["avaliacao"] = 0

    # Quantas pessoas avaliaram (escala logarítmica: 500+ avaliações = pontuação máxima).
    n = max(0, num_avaliacoes or 0)
    d["popularidade"] = round(min(1.0, math.log10(n + 1) / math.log10(501)) * PESOS["popularidade"])

    d["sem_site"] = 0 if tem_site_proprio(site) else PESOS["sem_site"]
    d["whatsapp"] = PESOS["whatsapp"] if eh_celular(whatsapp) else 0
    d["instagram"] = PESOS["instagram"] if (instagram or "").strip() else 0

    return Nota(total=sum(d.values()), detalhes=d)
