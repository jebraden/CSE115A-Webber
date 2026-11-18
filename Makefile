help: # :Print this message
	@echo "Targets: "
	@awk -F ':' '/^\S.+:/ { print " " $$1 " -> " $$3 }' Makefile

setup: # :Setup development environment
	scripts/setup.sh backend frontend

run-frontend: # :Run the frontend
	scripts/run-frontend.sh

run-backend: # :Run the backend
	scripts/run-backend.sh

test-offscreen: # :test the frontend and backend using a dummy display
	QT_QPA_PLATFORM=offscreen scripts/run-tests.sh backend frontend

test: # :test the frontend and backend using your actual window system
	scripts/run-tests.sh backend frontend

test-backend: # :Test the backend
	scripts/run-tests.sh backend

test-frontend-offscreen: # :Test the frontend using a dummy display
	QT_QPA_PLATFORM=offscreen scripts/run-tests.sh frontend

test-frontend: # :Test the frontend using your actual window system
	scripts/run-tests.sh frontend
