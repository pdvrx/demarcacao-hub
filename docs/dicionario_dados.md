# Dicionário de dados

## data/processed/terras.csv (uma linha por terra)
| Campo | Descrição |
|---|---|
| terra_id | ID interno estável (TI0001...). Nunca muda nem é reutilizado |
| nome | nome pela fonte de maior prioridade |
| ufs | UFs separadas por `;` |
| municipios | `Nome/UF` separados por `;` (união das fontes) |
| povos | povo(s), pela fonte de maior prioridade |
| area_ha | área em hectares, pela fonte de maior prioridade |
| modalidade | tradicionalmente_ocupada, reserva_indigena, dominial, interditada, nao_informada |
| fase | sem_providencia, em_estudo, delimitada, declarada, homologada, regularizada; ou especiais reserva_em_constituicao, restricao_de_uso; ou `indefinida` |
| fase_fonte | fonte da qual veio `fase` |
| fases_por_fonte | `fonte:fase` por fonte, separados por `\|` |
| divergencia_fase | `true` se as fontes trazem fases diferentes |
| precisao_geom | poligono, municipio, uf, nenhuma |
| sensivel | `true` se tratada como sensível (ver README) |
| fontes | fontes que citam a terra |
| n_registros | quantos registros das fontes foram vinculados |

## data/processed/juridico.csv (uma linha por registro de fonte com dados jurídicos/administrativos)
`terra_id, fonte, ato, ato_data, processo_funai, processos_judiciais, etapa, atuacao_administrativa, situacao_revisao,
sobreposicoes, observacoes, populacao, cr, reestudo, data_fonte`.
`ato` é o texto da fonte (ex.: "Decreto s/nº de 05/01/96"). `ato_data` é **inferida** do texto (ano de 2 dígitos: >=80 vira 19xx,
senão 20xx) e deve ser conferida antes de citar. `data_fonte` é a data de atualização informada pela própria fonte (Funai: `data_atual`).

## data/history/eventos.csv
`data_observacao, terra_id, nome, tipo (nova_terra | removida_da_base | mudanca), campo, valor_anterior, valor_novo`

## data/history/observacoes.csv
Uma linha por rodada: data, nº de terras, hash do estado, se houve mudança, nº de eventos.

## data/history/marcos_terra.csv
`terra_id, data_ato, precisao_data (dia|mes|ano), tipo_ato, numero_ato, orgao, descricao, fonte_url, verificado_em`

## data/history/marcos_gerais.csv
`data, precisao_data, tipo, titulo, descricao, fonte_url, status_verificacao`

## data/crosswalk/
- `terras_ids.csv`: terra_id, nome_canonico, criado_em
- `fontes_ids.csv`: fonte, chave_fonte, nome_original, ufs, terra_id, status (auto|novo|confirmado), score, atualizado_em
- `revisar.csv`: pares prováveis para conferência humana (coluna `decisao`: sim/nao)
- `pares_distintos.csv`: pares que você decidiu serem terras diferentes
- `fusoes.csv`: terras fundidas (terra_removida, terra_destino)
