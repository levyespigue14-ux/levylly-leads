from datetime import date, timedelta
from pathlib import Path


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cria_lead_com_nota_e_telefone_normalizado(lead):
    assert lead["whatsapp"] == "5511912345678"
    assert lead["status"] == "novo"
    assert lead["nota"] >= 90


def test_nao_aceita_whatsapp_repetido(client, lead):
    r = client.post("/leads", json={"nome": "Outra", "nicho": "x", "whatsapp": "11912345678"})
    assert r.status_code == 409


def test_explica_nota(client, lead):
    r = client.get(f"/leads/{lead['id']}/nota").json()
    assert set(r["detalhes"]) == {"avaliacao", "popularidade", "sem_site", "whatsapp", "instagram"}
    assert r["nota"] == lead["nota"]


def test_ciclo_abordagem_e_dois_followups(client, lead):
    lid = lead["id"]
    r = client.post(f"/leads/{lid}/abordagem").json()
    assert r["status"] == "abordado" and r["followup_em"]

    r = client.post(f"/leads/{lid}/followup").json()
    assert r["status"] == "followup" and r["followups_enviados"] == 1 and r["followup_em"]

    r = client.post(f"/leads/{lid}/followup").json()
    assert r["followups_enviados"] == 2 and r["followup_em"] is None   # depois do 2º, para de insistir

    assert client.post(f"/leads/{lid}/abordagem").status_code == 409


def test_socio_agenda_followup_e_guarda_objecao(client, lead):
    lid = lead["id"]
    client.post(f"/leads/{lid}/abordagem")
    r = client.post(f"/leads/{lid}/status", json={"status": "socio", "motivo": "vai falar com o sócio"}).json()
    assert r["status"] == "socio" and r["followup_em"]
    assert client.get("/funil/objecoes").json() == {"vai falar com o sócio": 1}


def test_followups_do_dia(client, lead):
    lid = lead["id"]
    client.post(f"/leads/{lid}/abordagem")
    hoje = date.today()
    assert client.get("/followups", params={"data": hoje.isoformat()}).json() == []
    futuro = (hoje + timedelta(days=10)).isoformat()
    assert [l["id"] for l in client.get("/followups", params={"data": futuro}).json()] == [lid]


def test_funil_conta_respostas_e_perdas_com_motivo(client):
    ids = []
    for i in range(4):
        r = client.post("/leads", json={"nome": f"Loja {i}", "nicho": "confeitaria",
                                        "whatsapp": f"1190000000{i}"}).json()
        ids.append(r["id"])
        client.post(f"/leads/{r['id']}/abordagem")
    client.post(f"/leads/{ids[0]}/status", json={"status": "respondeu"})
    client.post(f"/leads/{ids[1]}/status", json={"status": "perdido", "motivo": "já tem iFood"})
    client.post(f"/leads/{ids[2]}/status", json={"status": "fechado"})
    f = client.get("/funil").json()
    assert f["abordados"] == 4
    assert f["responderam"] == 3          # respondeu + perdido com motivo + fechado
    assert f["fecharam"] == 1
    assert f["taxa_resposta"] == 0.75
    assert client.get("/funil/objecoes").json() == {"já tem ifood": 1}


def test_proximos_ordena_pela_nota(client):
    client.post("/leads", json={"nome": "Fraca", "nicho": "sushi", "whatsapp": "11911111111",
                                "site": "https://fraca.com", "avaliacao": 3.9})
    client.post("/leads", json={"nome": "Forte", "nicho": "sushi", "whatsapp": "11922222222",
                                "instagram": "@forte", "avaliacao": 4.9, "num_avaliacoes": 400})
    nomes = [l["nome"] for l in client.get("/leads/proximos", params={"nicho": "sushi"}).json()]
    assert nomes == ["Forte", "Fraca"]


def test_importa_csv_de_exemplo(client):
    arquivo = Path(__file__).parent.parent / "data" / "exemplo_leads.csv"
    r = client.post("/importar/csv", files={"arquivo": ("leads.csv", arquivo.read_bytes(), "text/csv")}).json()
    assert r == {"importados": 6, "repetidos": 0, "invalidos": 0}
    again = client.post("/importar/csv", files={"arquivo": ("leads.csv", arquivo.read_bytes(), "text/csv")}).json()
    assert again["repetidos"] == 6
    leads = client.get("/leads", params={"nicho": "confeitaria"}).json()
    assert leads[0]["nome"] == "Doceria Exemplo"            # sem site, muitas avaliações
    assert leads[-1]["nome"] == "Confeitaria Modelo"        # já tem site próprio
