.PHONY: up down restart logs ps mqtt-logs db-logs api-shell meter ingestor psql

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

logs:
	docker compose logs -f

ps:
	docker ps

mqtt-logs:
	docker logs -f voltanet_mqtt

db-logs:
	docker logs -f voltanet_db

ingestor:
	cd services/api && . venv/bin/activate && python3 app/ingestor.py

meter:
	cd services/meter-agent && MQTT_HOST=127.0.0.1 MQTT_PORT=1884 cargo run

psql:
	docker exec -it voltanet_db psql -U voltanet_user -d voltanet