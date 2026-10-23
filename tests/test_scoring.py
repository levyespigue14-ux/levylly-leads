from app.scoring import calcular_nota, eh_celular, tem_site_proprio


def test_lead_ideal_tira_nota_alta():
    n = calcular_nota(avaliacao=5.0, num_avaliacoes=600, site="", whatsapp="(11) 91234-5678", instagram="@loja")
    assert n.total == 100


def test_site_proprio_tira_pontos_mas_instagram_nao_conta_como_site():
    com_site = calcular_nota(avaliacao=4.8, num_avaliacoes=100, site="https://loja.com.br",
                             whatsapp="11912345678", instagram="")
    so_insta = calcular_nota(avaliacao=4.8, num_avaliacoes=100, site="https://instagram.com/loja",
                             whatsapp="11912345678", instagram="")
    assert com_site.detalhes["sem_site"] == 0
    assert so_insta.detalhes["sem_site"] == 20
    assert so_insta.total - com_site.total == 20


def test_telefone_fixo_nao_conta_como_whatsapp():
    assert eh_celular("(11) 91234-5678")
    assert eh_celular("+55 11 91234-5678")
    assert not eh_celular("(86) 3200-0006")


def test_nota_baixa_e_sem_avaliacoes():
    n = calcular_nota(avaliacao=3.0, num_avaliacoes=0, site="https://x.com", whatsapp="", instagram="")
    assert n.total == 0


def test_links_que_nao_sao_site():
    for link in ("https://www.ifood.com.br/delivery/x", "http://linktr.ee/loja", "https://facebook.com/x"):
        assert not tem_site_proprio(link)
