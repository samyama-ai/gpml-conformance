.PHONY: repro test clean
repro:
	./run.sh
test:
	.venv/bin/pytest tests/ -q
clean:
	docker rm -f cf-neo4j cf-memgraph cf-age 2>/dev/null || true
	rm -rf __pycache__ src/__pycache__ tests/__pycache__
