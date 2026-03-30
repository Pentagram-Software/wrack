.PHONY: help setup web deploy-edge deploy-cloud deploy-ev3 deploy-ev3-release deploy-ev3-debug test test-deploy

help:
	@echo "Available commands:"
	@echo "  make web                 - Start web dev server (http://localhost:3000)"
	@echo "  make setup               - Install all dependencies"
	@echo "  make deploy-edge         - Deploy to Raspberry Pi"
	@echo "  make deploy-cloud        - Deploy GCP Cloud Functions"
	@echo "  make deploy-ev3          - Deploy to EV3 (release mode, requires EV3_HOST)"
	@echo "  make deploy-ev3-release  - Deploy to EV3 in release mode (requires EV3_HOST)"
	@echo "  make deploy-ev3-debug    - Deploy to EV3 in debug mode (requires EV3_HOST)"
	@echo "  make test                - Run all tests"
	@echo "  make test-deploy         - Run deployment script tests"
	@echo ""
	@echo "EV3 deployment examples:"
	@echo "  make deploy-ev3 EV3_HOST=192.168.1.100"
	@echo "  make deploy-ev3-debug EV3_HOST=192.168.1.100"

web:
	cd clients/web && npm install && npm run dev

setup:
	cd clients/web && npm install
	cd cloud/functions && pip install -r requirements.txt
	cd edge/video-streamer && pip install -r requirements.txt
	cd robot/controller && pip install -r requirements.txt

deploy-cloud:
	cd cloud/functions && gcloud functions deploy

deploy-edge:
	rsync -av --exclude='__pycache__' --exclude='*.pyc' \
		edge/ pi@raspberrypi.local:/home/pi/robot/edge/

test:
	cd edge/video-streamer && python -m pytest tests/
	cd robot/controller && python -m pytest tests/
	cd clients/web && npm test

test-deploy:
	cd robot/controller && python -m pytest scripts/tests/ -v

# EV3 Deployment targets
# Usage: make deploy-ev3 EV3_HOST=<ip_address>
deploy-ev3: deploy-ev3-release

deploy-ev3-release:
ifndef EV3_HOST
	$(error EV3_HOST is not set. Usage: make deploy-ev3-release EV3_HOST=192.168.1.100)
endif
	cd robot/controller && python3 scripts/deploy_ev3.py --host $(EV3_HOST) --mode release

deploy-ev3-debug:
ifndef EV3_HOST
	$(error EV3_HOST is not set. Usage: make deploy-ev3-debug EV3_HOST=192.168.1.100)
endif
	cd robot/controller && python3 scripts/deploy_ev3.py --host $(EV3_HOST) --mode debug

deploy-ev3-list:
	cd robot/controller && python3 scripts/deploy_ev3.py --list-files
