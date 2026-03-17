.PHONY: help setup deploy-edge deploy-cloud test

help:
	@echo "Available commands:"
	@echo "  make setup          - Install all dependencies"
	@echo "  make deploy-edge    - Deploy to Raspberry Pi"
	@echo "  make deploy-cloud   - Deploy GCP Cloud Functions"
	@echo "  make test           - Run all tests"

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
