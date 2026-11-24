PY ?= python

setup:
	$(PY) -m pip install -r requirements.txt

ref:        ## baixa municípios/UFs (IBGE) para geolocalizar terras sem polígono
	$(PY) -m demarcacao fetch-ref

update:     ## pipeline completo: ingest -> match -> build -> snapshot -> export -> validate
	$(PY) -m demarcacao update

status:
	$(PY) -m demarcacao status

test:
	$(PY) -m pytest -q

site:       ## abre o site local em http://localhost:8000
	$(PY) -m http.server 8000 -d site
