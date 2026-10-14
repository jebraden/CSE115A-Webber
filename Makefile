help: # :Print this message
	@echo "Targets: "
	@awk -F ':' '/^\S.+:/ { print " " $$1 " -> " $$3 }' Makefile

setup: # :Setup development environment
	scripts/setup.sh backend frontend

run-frontend: # :Run the frontend
	scripts/run-frontend.sh

run-backend: # :Run the backend
	scripts/run-backend.sh

test: test-frontend test-backend # :Test the frontend and backend

test-backend: # :Test the backend
	-scripts/run-tests.sh backend

test-frontend: # :Test the frontend
	-scripts/run-tests.sh frontend
