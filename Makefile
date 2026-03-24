PROJECT_ID ?= $(shell gcloud config get-value project)
REGION     ?= us-central1
IMAGE_URI  ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/product-intel/product-intel-agent:latest

.PHONY: install dev build push deploy tf-init tf-apply

install:
	uv sync

dev:
	uv run uvicorn agent.fast_api_app:app --reload --port 8080

build:
	docker build -t $(IMAGE_URI) .

push: build
	docker push $(IMAGE_URI)

deploy: push
	cd deployment/terraform && terraform apply \
		-var="project_id=$(PROJECT_ID)" \
		-var="region=$(REGION)" \
		-var="image_uri=$(IMAGE_URI)" \
		-var="serper_api_key=$(SERPER_API_KEY)"

tf-init:
	cd deployment/terraform && terraform init

tf-apply:
	cd deployment/terraform && terraform apply \
		-var="project_id=$(PROJECT_ID)" \
		-var="region=$(REGION)" \
		-var="image_uri=$(IMAGE_URI)" \
		-var="serper_api_key=$(SERPER_API_KEY)"
