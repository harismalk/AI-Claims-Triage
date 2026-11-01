.PHONY: db seed

db:
	docker compose up -d

seed:
	.venv/bin/python -m app.generate_data --seed 42
