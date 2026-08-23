setup:
	python -m pip install -r requirements.txt

generate-data:
	python -m data.generator.generate --events 100000 --seed 42

seed:
	python -m data.generator.generate --events 100000 --seed 42 > /tmp/fluxpay_seed.csv

run:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q
