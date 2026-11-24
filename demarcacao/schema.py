"""Vocabulário canônico do projeto."""

# Ordem = avanço do procedimento administrativo (Decreto 1.775/1996), do menos ao mais avançado.
FASES = ["sem_providencia", "em_estudo", "delimitada", "declarada", "homologada", "regularizada"]
# Categorias que NÃO fazem parte da sequência acima (rito diferente); ver docs/metodologia.md
FASES_ESPECIAIS = ["reserva_em_constituicao", "restricao_de_uso"]
FASE_INDEFINIDA = "indefinida"

FASE_ROTULOS = {
    "sem_providencia": "Sem providência / reivindicada",
    "em_estudo": "Em estudo (identificação)",
    "delimitada": "Delimitada (relatório aprovado)",
    "declarada": "Declarada (portaria declaratória)",
    "homologada": "Homologada (decreto)",
    "regularizada": "Regularizada (registrada)",
    "reserva_em_constituicao": "Encaminhada como Reserva Indígena",
    "restricao_de_uso": "Restrição de ingresso/uso",
    FASE_INDEFINIDA: "Indefinida (rótulo não mapeado)",
}

MODALIDADES = ["tradicionalmente_ocupada", "reserva_indigena", "dominial", "interditada", "nao_informada"]

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

# Colunas padronizadas que toda fonte produz em data/interim/<fonte>.csv
INTERIM_COLS = [
    "fonte", "chave_fonte", "nome_original", "nome_norm", "ufs", "municipios",
    "povos", "area_ha", "fase_origem", "fase", "modalidade", "extras",
]

# Colunas de data/processed/terras.csv
TERRAS_COLS = [
    "terra_id", "nome", "ufs", "municipios", "povos", "area_ha", "modalidade",
    "fase", "fase_fonte", "fases_por_fonte", "divergencia_fase",
    "precisao_geom", "sensivel", "fontes", "n_registros",
]

# Campos cuja mudança vira evento no histórico
CAMPOS_MONITORADOS = ["nome", "fase", "modalidade", "precisao_geom", "area_ha", "ufs", "divergencia_fase"]

# Campos jurídicos/administrativos extras (config/sources.yml -> extras), consolidados em data/processed/juridico.csv
JURIDICO_COLS = [
    "terra_id", "fonte", "ato", "ato_data", "processo_funai", "processos_judiciais", "etapa",
    "atuacao_administrativa", "situacao_revisao", "sobreposicoes", "observacoes", "populacao",
    "cr", "reestudo", "data_fonte",
]
