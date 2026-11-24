from demarcacao.normalize import (map_fase, map_modalidade, normalize_name, parse_float_br,
                                  parse_municipios, split_ufs)


def test_normalize_name_remove_prefixos_e_acentos(proj):
    assert normalize_name("Terra Indígena Raposa Serra do Sol") == "raposa serra sol"
    assert normalize_name("T.I. Ibirama-La Klãnõ") == "ibirama la klano"
    assert normalize_name("Reserva Indígena Xakriabá") == "xakriaba"


def test_ufs_e_numeros():
    assert split_ufs("MG/ba") == ["BA", "MG"]
    assert parse_float_br("1.234,56") == 1234.56
    assert parse_float_br("28926,1102") == 28926.1102
    assert parse_float_br("263.130") == 263130.0
    assert parse_float_br("") is None


def test_municipios():
    assert parse_municipios("Altamira, Anapu/PA; Porto Velho - RO") == [
        ("Altamira", None), ("Anapu", "PA"), ("Porto Velho", "RO")]


def test_fases(proj):
    assert map_fase("Homologada - Registrada em Cartório") == "regularizada"
    assert map_fase("Declarada") == "declarada"
    assert map_fase("Em identificação") == "em_estudo"
    assert map_fase("Identificada") == "delimitada"
    assert map_fase("Reivindicada") == "sem_providencia"
    assert map_fase("Não regularizada") == ""      # deliberadamente não mapeado
    assert map_fase("algo estranho") == ""
    assert map_modalidade("Reserva Indígena") == "reserva_indigena"
