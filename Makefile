help: # :Print this message
	@echo "Targets: "
	@awk -F ':' '/^\S.+:/ { print " " $$1 " -> " $$3 }' Makefile

setup: # :Setup development environment
	scripts/setup.sh backend frontend

run-frontend: # :Run the frontend
	scripts/run-frontend.sh

run-backend: # :Run the backend
	scripts/run-backend.sh

install-browser: # :Install the Chromium browser used to archive pages
	frontend/venv/bin/python -m playwright install chromium

run-demo: # :Run the offline UI with sample data
	scripts/run-frontend.sh --demo

test-integration: # :Archive a temporary website, stop its server and view the saved copy
	WEBBER_RUN_ARCHIVE_E2E=1 QT_QPA_PLATFORM=offscreen frontend/venv/bin/python -m pytest frontend/tests/test_archive_e2e.py

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
