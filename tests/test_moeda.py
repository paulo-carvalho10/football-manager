"""A moeda e so exibicao: o motor conta em euro e a ida e volta nao perde dinheiro."""

from fm.moeda import do_euro, json_da_moeda, moeda_do_pais, para_euro, texto


def test_cada_pais_na_sua_moeda():
    assert moeda_do_pais("BRA") == "BRL"
    assert moeda_do_pais("ENG") == "GBP"
    assert moeda_do_pais("ARG") == "USD"
    assert moeda_do_pais("ESP") == "EUR"
    assert moeda_do_pais(None) == "EUR"
    assert json_da_moeda("BRA")["simbolo"] == "R$"


def test_a_ida_e_volta_nao_perde_dinheiro():
    for moeda in ("BRL", "GBP", "USD", "EUR"):
        for v in (1_000, 250_000, 12_345_678):
            assert abs(para_euro(do_euro(v, moeda), moeda) - v) <= 1


def test_o_texto_das_mensagens():
    assert texto(65_300_000) == "€ 65,3 mi"
    assert texto(10_000_000, "BRL") == "R$ 62,0 mi"
    assert texto(-500_000) == "−€ 500 mil"
