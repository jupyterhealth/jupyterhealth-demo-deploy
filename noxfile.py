import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import nox
import yaml

cluster_name = os.getenv("CLUSTER_NAME", "demo")
jhe_name = os.getenv("JHE_NAME")

if jhe_name is None:
    sys.exit("Must set $JHE_NAME to the current deployment: export JHE_NAME=staging")

ROOT = Path(__file__).parent.resolve()
CHARTS = ROOT / "charts"
SUPPORT_CHART = CHARTS / "support"
JHE_CHART = CHARTS / "jhe"


def cluster_dir(cluster_name):
    return ROOT / "clusters" / cluster_name


def config_dir(cluster_name):
    return ROOT / "config" / cluster_name


def load_kubeconfig(session, cluster_name: str, kubeconfig: Path) -> None:
    cluster_path = cluster_dir(cluster_name)
    creds_file = cluster_path / "creds.dec.yaml"
    with creds_file.open() as f:
        creds = yaml.safe_load(f)
    # don't include AWS env
    env = {key: var for key, var in os.environ.items() if not key.startswith("AWS_")}
    env["AWS_ACCESS_KEY"] = creds["aws"]["access_key"]
    env["AWS_SECRET_KEY"] = creds["aws"]["secret_key"]
    env["AWS_REGION"] = creds["aws"]["region"]
    aws_cluster_name = creds["aws"].get("cluster_name", cluster_name)
    env["KUBECONFIG"] = kubeconfig
    session.run(
        "aws",
        "eks",
        "update-kubeconfig",
        "--name",
        aws_cluster_name,
        env=env,
        external=True,
    )


def set_kubeconfig(session, cluster_name: str) -> None:
    cluster_path = cluster_dir(cluster_name)
    kubeconfig = cluster_path / "kubeconfig.dec.yaml"
    os.environ["KUBECONFIG"] = str(kubeconfig)
    if not kubeconfig.exists():
        load_kubeconfig(session, cluster_name, kubeconfig)
    assert kubeconfig.exists()


def get_values_args(*values_dirs):
    args = []
    for values_dir in values_dirs:
        for values_yaml in values_dir.rglob("*.yaml"):
            if ".enc." not in values_yaml.name:
                args.extend(["--values", str(values_yaml)])
    return args


def decrypt_file(session, src: Path):
    dest = src.parent / src.name.replace(".enc.", ".dec.")
    assert dest != src
    session.run("sops", "decrypt", src, "--output", dest, external=True)


@nox.session(python=False)
def decrypt(session):
    cluster_path = cluster_dir(cluster_name)
    for parent_dir in (cluster_path, config_dir(jhe_name), config_dir("_common")):
        for src in parent_dir.rglob("*.enc.*"):
            decrypt_file(session, src)


@nox.session(python=False)
def kubectl(session):
    decrypt(session)
    set_kubeconfig(session, cluster_name)
    session.run("kubectl", *session.posargs, external=True)


@nox.session(python=False)
def helm_support_upgrade_crds(session):
    decrypt(session)
    set_kubeconfig(session, cluster_name)
    session.run("helm", "dependency", "update", SUPPORT_CHART, external=True)
    # apply any CRD upgrades (e.g. cert-manager, envoy gateway)
    # helm cannot upgrade CRDs
    # from https://github.com/traefik/traefik-helm-chart?tab=readme-ov-file#upgrade-the-standalone-traefik-chart
    with NamedTemporaryFile() as f:
        session.run("helm", "show", "crds", SUPPORT_CHART, external=True, stdout=f)
        f.flush()
        session.run(
            "kubectl",
            "apply",
            "--server-side",
            "--force-conflicts",
            "-f",
            f.name,
            external=True,
        )


@nox.session(python=False)
def helm_support(session):
    decrypt(session)
    cluster_path = cluster_dir(cluster_name)
    set_kubeconfig(session, cluster_name)
    session.run("helm", "dependency", "update", SUPPORT_CHART, external=True)
    values_args = get_values_args(cluster_path / "support") + get_values_args()
    values_args = get_values_args(cluster_path / "support")

    session.run(
        "helm",
        "upgrade",
        "--install",
        "--namespace=support",
        "support",
        SUPPORT_CHART,
        *values_args,
        external=True,
    )


@nox.session(python=False)
def helm_jhe(session):
    decrypt(session)
    common_path = config_dir("_common")
    jhe_path = config_dir(jhe_name)
    assert common_path.exists()
    assert jhe_path.exists()
    set_kubeconfig(session, cluster_name)
    session.run("helm", "dependency", "update", JHE_CHART, external=True)
    values_args = get_values_args(common_path, jhe_path)

    session.run(
        "helm",
        "upgrade",
        "--install",
        "--namespace",
        jhe_name,
        jhe_name,
        JHE_CHART,
        *values_args,
        external=True,
    )
