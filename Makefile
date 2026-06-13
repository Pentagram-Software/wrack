.PHONY: help setup web deploy-edge deploy-cloud deploy-ev3 deploy-ev3-release deploy-ev3-debug deploy-robot deploy-robot-dry-run test test-deploy

# ---------------------------------------------------------------------------
# EV3 rsync-based deployment configuration
# Values are loaded from robot/controller/deploy.conf (if present) and can be
# overridden by environment variables or make command-line arguments:
#   EV3_IP=1.2.3.4 make deploy-robot
# ---------------------------------------------------------------------------
-include robot/controller/deploy.conf
EV3_IP ?= 192.168.1.83
EV3_USER ?= robot
EV3_SSH_PORT ?= 22
EV3_REMOTE_PATH ?= /home/robot/controller

help:
	@echo "Available commands:"
	@echo "  make web                    - Start web dev server (http://localhost:3000)"
	@echo "  make setup                  - Install all dependencies"
	@echo "  make deploy-edge            - Deploy to Raspberry Pi"
	@echo "  make deploy-cloud           - Deploy GCP Cloud Functions"
	@echo "  make deploy-robot           - Deploy robot/controller to EV3 (rsync --checksum)"
	@echo "  make deploy-robot-dry-run   - Show what deploy-robot would transfer (no transfer)"
	@echo "  make deploy-ev3             - Deploy to EV3 (release mode, requires EV3_HOST)"
	@echo "  make deploy-ev3-release     - Deploy to EV3 in release mode (requires EV3_HOST)"
	@echo "  make deploy-ev3-debug       - Deploy to EV3 in debug mode (requires EV3_HOST)"
	@echo "  make test                   - Run all tests"
	@echo "  make test-deploy            - Run deployment script tests"
	@echo ""
	@echo "EV3 rsync deployment (deploy-robot / deploy-robot-dry-run):"
	@echo "  Reads defaults from robot/controller/deploy.conf; override via env vars:"
	@echo "  EV3_IP=1.2.3.4 make deploy-robot"
	@echo "  EV3_IP=1.2.3.4 EV3_SSH_PORT=2222 make deploy-robot"
	@echo ""
	@echo "EV3 legacy deployment (deploy-ev3):"
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

deploy-bigquery:
	cd cloud/bigquery && ./deploy.sh

deploy-edge:
	rsync -av --exclude='__pycache__' --exclude='*.pyc' \
		edge/ pi@raspberrypi.local:/home/pi/robot/edge/

# ---------------------------------------------------------------------------
# Smart EV3 deployment: rsync --checksum (only transfers changed files)
# Config: robot/controller/deploy.conf  |  override: EV3_IP=x make deploy-robot
# ---------------------------------------------------------------------------
deploy-robot:
	@[ -n "$(EV3_IP)" ] || { echo "Error: EV3_IP is not set."; echo "  Set it in robot/controller/deploy.conf or run: EV3_IP=<host> make deploy-robot"; exit 1; }
	@echo "==> Deploying robot/controller to $(EV3_USER)@$(EV3_IP):$(EV3_REMOTE_PATH) (ssh port $(EV3_SSH_PORT))"
	@START=$$(date +%s); \
	 python3 robot/controller/scripts/deploy_ev3.py \
	   --host "$(EV3_IP)" \
	   --user "$(EV3_USER)" \
	   --port "$(EV3_SSH_PORT)" \
	   --path "$(EV3_REMOTE_PATH)" \
	   --method tar \
	   --verbose; \
	 EXIT=$$?; END=$$(date +%s); \
	 echo "==> Elapsed: $$((END - START))s"; \
	 exit $$EXIT

deploy-robot-dry-run:
	@[ -n "$(EV3_IP)" ] || { echo "Error: EV3_IP is not set."; echo "  Set it in robot/controller/deploy.conf or run: EV3_IP=<host> make deploy-robot-dry-run"; exit 1; }
	@echo "==> DRY RUN — would deploy robot/controller to $(EV3_USER)@$(EV3_IP):$(EV3_REMOTE_PATH) (ssh port $(EV3_SSH_PORT))"
	@python3 robot/controller/scripts/deploy_ev3.py \
	  --host "$(EV3_IP)" \
	  --user "$(EV3_USER)" \
	  --port "$(EV3_SSH_PORT)" \
	  --path "$(EV3_REMOTE_PATH)" \
	  --method tar \
	  --dry-run \
	  --verbose
	@echo "==> Dry run complete — no files transferred"

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
