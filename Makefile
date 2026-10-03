.PHONY: repro test clean verify-adapter separation beds
repro:
	./run.sh
test:
	.venv/bin/pytest tests/ -q
clean:
	docker rm -f cf-neo4j cf-neo4j-2026 cf-memgraph cf-age cf-arcade cf-falkor \
	  cf-surreal cf-spanner 2>/dev/null || true
	rm -rf __pycache__ src/__pycache__ tests/__pycache__

# What a contributor runs before opening a pull request that adds an engine.
verify-adapter:
	.venv/bin/python tools/verify_adapter.py $(ENGINE)

separation:
	.venv/bin/python tools/separation.py

beds:
	.venv/bin/python tools/choose_beds.py
