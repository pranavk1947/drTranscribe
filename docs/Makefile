# LiveRx — GCP Setup & Deployment Makefile
# Usage: make setup-all   (one-time GCP setup)
#        make deploy       (build + push + deploy)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
PROJECT_ID       := loophealth-patient-dev
REGION           := asia-south1
SERVICE_NAME     := liverx
AR_REPO          := liverx
SA_NAME          := liverx-deployer
SA_EMAIL         := $(SA_NAME)@$(PROJECT_ID).iam.gserviceaccount.com
IMAGE            := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(AR_REPO)/$(SERVICE_NAME)
TAG              := $(shell git rev-parse --short HEAD)

# ──────────────────────────────────────────────
# One-time GCP Setup
# ──────────────────────────────────────────────

.PHONY: setup-all setup-project setup-apis setup-registry setup-sa setup-sa-key

setup-all: setup-project setup-apis setup-registry setup-sa setup-sa-key
	@echo "\n✅ GCP setup complete. Add liverx-sa-key.json contents to GitHub secret LIVERX_GCP_SA_KEY"

setup-project:
	gcloud config set project $(PROJECT_ID)

setup-apis:
	gcloud services enable \
		run.googleapis.com \
		artifactregistry.googleapis.com \
		iam.googleapis.com

setup-registry:
	gcloud artifacts repositories create $(AR_REPO) \
		--repository-format=docker \
		--location=$(REGION) \
		--description="LiveRx Docker images" \
		|| echo "Registry already exists"

setup-sa:
	gcloud iam service-accounts create $(SA_NAME) \
		--display-name="LiveRx CI/CD Deployer" \
		|| echo "Service account already exists"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/run.admin"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/artifactregistry.writer"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/iam.serviceAccountUser"

setup-sa-key:
	gcloud iam service-accounts keys create liverx-sa-key.json \
		--iam-account=$(SA_EMAIL)
	@echo "\n🔑 Key saved to liverx-sa-key.json"
	@echo "   Paste its contents into GitHub secret: LIVERX_GCP_SA_KEY"
	@echo "   Then delete the local file: rm liverx-sa-key.json"

# ──────────────────────────────────────────────
# Local Build & Deploy (manual)
# ──────────────────────────────────────────────

.PHONY: build push deploy docker-auth

docker-auth:
	gcloud auth configure-docker $(REGION)-docker.pkg.dev --quiet

build:
	docker build -t $(IMAGE):$(TAG) -t $(IMAGE):latest .

push: docker-auth
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest

deploy: build push
	gcloud run deploy $(SERVICE_NAME) \
		--image=$(IMAGE):$(TAG) \
		--region=$(REGION) \
		--platform=managed
	@echo "\n✅ Deployed $(IMAGE):$(TAG)"
	@gcloud run services describe $(SERVICE_NAME) --region=$(REGION) --format="value(status.url)"

# ──────────────────────────────────────────────
# Development
# ──────────────────────────────────────────────

.PHONY: run lint format typecheck

run:
	python -m src.main

lint:
	ruff check src/

format:
	ruff format src/

typecheck:
	mypy src/ --ignore-missing-imports
