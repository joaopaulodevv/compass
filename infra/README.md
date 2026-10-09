# Infrastructure

Local development infrastructure is defined in the repository root `docker-compose.yml`
(API, PostgreSQL, Redis).

This directory is reserved for infrastructure that outgrows a single Compose file:
deployment manifests, provisioning scripts, and environment-specific configuration.
It is intentionally empty of such assets today - nothing is deployed anywhere yet.
