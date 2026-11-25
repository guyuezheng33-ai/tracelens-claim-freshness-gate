.PHONY: verify graph test

verify:
	bash scripts/award-verify.sh

graph:
	bash scripts/graph.sh

test:
	cd trace-lens && python -m pytest tests -q
