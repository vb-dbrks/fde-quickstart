---
title: Deploy and CI/CD
---

# Deploy and CI/CD

The app, its Lakebase project and an MLflow experiment are deployed together with a Declarative
Automation Bundle (`databricks.yml`, `resources/`). Each target (`dev`, `test`, `prod`) pins its
workspace host, so deploying with a profile for another workspace fails instead of landing in the
wrong place.

## What a target creates

| Resource | File | Notes |
| --- | --- | --- |
| The app | `resources/app.app.yml` | Start command and environment in `app.yaml`. Resources: the database, the model endpoint (`CAN_QUERY`), the experiment (`CAN_EDIT`). |
| Lakebase project, role, database | `resources/lakebase.postgres.yml` | One project per target, `<name>-<target>`. The app's service principal gets `CAN_CONNECT_AND_CREATE`. Prod has `prevent_destroy`. |
| MLflow experiment | `resources/mlflow.experiment.yml` | Receives a trace per agent run. |

The app installs from `pyproject.toml` and `uv.lock` on Databricks Apps; there is no
`requirements.txt`. The built frontend (`backend/static/`) is ignored by git and included in the
bundle explicitly.

## Deploying from your machine

```bash
make deploy TARGET=dev PROFILE=<cli-profile>
```

This checks that `make init` filled in every placeholder, builds the frontend, validates the bundle
with `--strict`, deploys it and starts the app. On first start the app creates its schema and tables.
`make destroy TARGET=dev PROFILE=<cli-profile>` removes a target (it asks first).

Development mode doesn't make the app or Lakebase names per-user, so the dev target is shared: one
person, or CI, deploys dev per workspace.

## CI/CD

Both pipelines run the same checks on every change, and deploy with workload identity federation: the
pipeline's identity token is exchanged for a Databricks token for a service principal, so no
Databricks secret is stored in GitHub or GitLab. Deploys use `make ci-deploy TARGET=...`, which
authenticates through environment variables and refuses to run outside CI.

| | GitHub Actions | GitLab CI |
| --- | --- | --- |
| Checks | `.github/workflows/ci.yml`: Python (ruff, mypy, pytest), frontend (ESLint, tsc, Vitest, build), lockfiles and generated API types | `.gitlab-ci.yml`: the same jobs in the `check` stage |
| Deploy | `.github/workflows/deploy.yml`: dev on push to `main`; test and prod by running the workflow by hand | `deploy-dev` on the default branch; `deploy-test` and `deploy-prod` as manual jobs |
| Auth | `DATABRICKS_AUTH_TYPE=github-oidc`; per environment `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` | `DATABRICKS_AUTH_TYPE=env-oidc`; `DATABRICKS_ACCOUNT_ID`, and per environment `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` |
| Switch | Deploys run once the repository variable `DEPLOY_ENABLED` is `true` | Deploy jobs appear once the variable `DEPLOY_ENABLED` is `true` |

The README's **CI/CD** section lists the setup steps: the service principals, their federation
policies, and the variables. Protect prod with required reviewers (GitHub environments) or protected
environments (GitLab).

## Lockfiles

`uv.lock` and the npm lockfiles must reference only the public registries, or CI and Databricks Apps
deploys fail. `scripts/check_lockfiles.sh` checks this in CI; `make lock` updates them safely on a
machine that uses a package mirror.
