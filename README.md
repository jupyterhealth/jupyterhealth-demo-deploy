# jupyterhealth-demo-deploy

Deployment configuration for JupyterHealth demo at Berkeley.

## Structure

This repo contains two charts:

1. `support` which contains per-cluster resources (Gateway, prometheus, grafana, cert-manager)
1. `jhe` which deploys JupyterHealth exchange

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

## Notes

Setting up deployment from OIDC is tedious, but useful because there are no credentials to manage.
Documentation is scattered, but thoroughly linked.

Sources:

- https://docs.github.com/en/actions/concepts/security/openid-connect
- https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
- https://github.com/aws-actions/configure-aws-credentials

Steps:

1. Add GitHub as an OIDC IdentityProvider in AWS IAM, with inputs:

   - url: `https://token.actions.githubusercontent.com`
   - audience: `sts.amazonaws.com`
   - [ref](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws#adding-the-identity-provider-to-aws)

1. create a Role for GitHub deployments.
   a. It needs a Trust Relationship to trust the Identity Provider. We use a `deploy` environment on the repo to manage access:

   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Principal": {
                   "Federated": "arn:aws:iam::123:oidc-provider/token.actions.githubusercontent.com"
               },
               "Action": "sts:AssumeRoleWithWebIdentity",
               "Condition": {
                   "StringEquals": {
                       "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                       "token.actions.githubusercontent.com:sub": "repo:jupyterhealth/jupyterhealth-demo-deploy:environment:deploy"
                   }
               }
           }
       ]
   }
   ```

   b. it needs permission to decrypt with sops and retrieve `kubeconfig`. Use the `arn` in `.sops.yaml`.
   Create the permissions:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "GetKubeConfig",
         "Effect": "Allow",
         "Action": "eks:DescribeCluster",
         "Resource": "*"
       },
       {
         "Sid": "SopsDecrypt",
         "Effect": "Allow",
         "Action": "kms:Decrypt",
         "Resource": "arn:aws:kms:us-east-2:123:key/u-u-i-d"
       }
     ]
   }
   ```

1. Grant the Role access ClusterAdmin on our cluster.
   In EKS > {cluster} > Access, add our `role/github-deploy` with `AmazonEKSClusterAdminPolicy` to make it a cluster admin.

1. (back on GitHub) create an Environment called `deploy` (must match `environment:` in the Trust Relationship) with appropriate branch protection rules

1. in a GitHub Actions workflow, add:

   ```yaml
   environment: deploy
   ```

   and the step:

   ```yaml
   - name: Configure AWS Credentials
     uses: aws-actions/configure-aws-credentials@ec61189d14ec14c8efccab744f656cffd0e33f37 # v6.1.0
     with:
       role-to-assume: arn:aws:iam::703671906202:role/github-deploy
       aws-region: us-east-2
   ```

Now we are at the point where any github action with access to the `deploy` environment can

1. authenticate with AWS and assume the `github-deploy` Role (IAM IdentityProvider and Role Trust relationship)
1. decrypt with `sops` (`kms:Decrypt` scope)
1. fetch KUBECONFIG via `aws eks update-kubeconfig` (`eks:DescribeCluster`)
1. administer the cluster (currently all clusters, since this is a single-purpose AWS project) (`AmazonEKSClusterAdminPolicy`), and therefore deploy from helm
