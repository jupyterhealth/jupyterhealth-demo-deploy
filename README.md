# jupyterhealth-demo-deploy

Deployment configuration for JupyterHealth demo at Berkeley.

## Structure

This repo contains two charts:

1. `support` which contains per-cluster resources (Gateway, prometheus, grafana, cert-manager)
2. `jhe` which deploys JupyterHealth exchange

For each _cluster_ `support` is deployed once.
For each _deployment_, `jhe` is deployed once.

Currently, we have one cluster (`demo`) and two deployments (`staging` and `demo`), both on that cluster.

## Deployment (nox, helm)

Deployment is done through `helm` via `nox`.

`helm` manages deployments on Kubernetes.

`nox` is our task runner to encapsulate the steps of things we do from this repo.

List available operations:

```
nox --list-sessions
```

To deploy the support chart for a cluster:

```
nox -s helm_support
```

To deploy the jhe chart for an instance:

```
nox -s helm_jhe
```

In order for these commands to work, files encrypted with `sops` must be decrypted (see below).
This generally means being logged in with the aws cli.

TODO: Authenticate deployment from GitHub using GitHub Actions OIDC.


## Secrets with SOPS

Secrets are managed using [sops](https://getsops.io).
Files containing sensitive information are named `$name.enc.$ext`, such as `clusters/demo/creds.enc.yaml`,
and are encoded with `sops`.
The key is managed via AWS KMS, and authenticated with AWS credentials, e.g.

```
aws sso login
```

For example, min stores the credentials for this deployment in his `health` profile,
so must set

```bash
export AWS_PROFILE=health
```

for most commands to work.

To edit a sops-encrypted file, run:

```bash
sops edit clusters/demo/creds.enc.yaml
```

and you will get an editor with the decrypted contents of the file.
sops will then write back the updated encrypted file.
