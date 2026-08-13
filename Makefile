.PHONY: data etl db load readout api web test lint

data:
	python -m analytics.download_data

etl:
	python -m analytics.etl_listings

db:
	docker compose up -d db

load:
	python -m analytics.load_database

readout:
	python -m analytics.run_analysis

pipeline:
	python -m analytics.pipeline --readout

api:
	uvicorn api.main:app --reload --port 8010

web:
	cd web && npm run dev

test:
	pytest -m "not integration"
	pytest -m integration

lint:
	ruff check analytics api tests
