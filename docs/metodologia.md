# Metodologia (rascunho para completar)

## Fontes
Liste aqui, para cada fonte: instituição, arquivo, data de publicação/acesso, URL, licença/termos de uso.
O pipeline registra automaticamente nome do arquivo, sha256 e datas em `data/interim/ingest_meta.json`.

## Fases
Vocabulário canônico (ordem do procedimento administrativo): `sem_providencia`, `em_estudo`, `delimitada`,
`declarada`, `homologada`, `regularizada`. O mapeamento dos rótulos de cada fonte está em `config/fases.yml`
(regras avaliadas em ordem). Rótulos sem regra viram `fase` vazia na fonte e aparecem em
`relatorios/fases_nao_mapeadas.csv`. Defina e justifique aqui as equivalências (por exemplo, ISA "Identificada" ~ Funai "Delimitada").

## Categorias fora da sequência
`reserva_em_constituicao` (rótulo "Encaminhada RI" na Funai e no MPF) e `restricao_de_uso` ("Com restrição de ingresso")
não são etapas do rito demarcatório (Decreto 1.775/1996) e por isso não entram na escala de `sem_providencia` a `regularizada`.
Confirme as definições com a Funai antes de citar. "Dominial Indígena" é tratada como modalidade, não como fase.

## Reconciliação entre fontes
1. Cada fonte é padronizada (`data/interim/<fonte>.csv`).
2. Nomes são normalizados (sem acento, sem "Terra Indígena"/"TI", sem preposições) e comparados por similaridade
   (limiares em `config/settings.yml`), restritos a terras que compartilham UF. A chave de comparação ignora prefixos,
UF final e "(RI)", e trata k=c, y=i, ss=c e apóstrofos como equivalentes (Xukuru=Xucuru, Zo’é=Zoe).
3. Acima do limiar automático e com **uma única** candidata, o vínculo é criado (`status=auto`); empate entre candidatas vai para revisão. Abaixo, nasce uma terra nova (`status=novo`) e, se
   houver candidata parecida, o par vai para `revisar.csv`.
4. Vínculos revisados à mão (`status=confirmado`) nunca são reescritos.
5. Uma fonte não vincula dois registros seus à mesma terra, exceto as marcadas `permite_varias_linhas`.

Prioridade de fontes para nome, área e fase: `prioridade_fontes` em `config/settings.yml`. Quando as fases das fontes
diferem, `divergencia_fase=true` e `fases_por_fonte` mostra cada valor. **Divergência não é erro**: pode refletir defasagem
de atualização ou critérios distintos.

## Localização
`poligono` (Funai) > `municipio` (ponto representativo do município, IBGE) > `uf` > `nenhuma`.
Pontos são aproximados e **não delimitam o território reivindicado**.

## Histórico
Ver README, seção "Histórico: dois tipos de data".

## Ética
Defina aqui a política para povos isolados, o tratamento de nomes de povos e o diálogo com organizações indígenas.
