"""Stage 5, offline: the deployment files are valid and agree with each other and with the code.

Nothing here reaches Azure. azure.yaml is checked against azd's own schemas, vendored in
infra/schemas/. The Bicep files are linted by the Bicep CLI in CI (.github/workflows/evals.yml).
"""
import json
import re
from pathlib import Path

import yaml
from jsonschema import validators
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

ROOT = Path(__file__).parent.parent
SCHEMAS = ROOT / "infra" / "schemas"
RAW = "https://raw.githubusercontent.com/Azure/azure-dev/main/"
AZURE_YAML = yaml.safe_load((ROOT / "azure.yaml").read_text(encoding="utf-8"))
SERVICES = AZURE_YAML["services"]


def registry():
    resources = []
    for path in SCHEMAS.rglob("*.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        url = contents.get("$id") or RAW + path.relative_to(SCHEMAS).as_posix()
        resources.append((url, Resource.from_contents(contents, default_specification=DRAFT7)))
    return Registry().with_resources(resources)


def test_azure_yaml_matches_the_azd_schema():
    schema = json.loads((SCHEMAS / "schemas" / "v1.0" / "azure.yaml.json").read_text(encoding="utf-8"))
    validator = validators.validator_for(schema)(schema, registry=registry())
    errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator.iter_errors(AZURE_YAML)]
    assert not errors, "\n".join(errors)


def test_every_service_a_service_uses_exists():
    for name, service in SERVICES.items():
        assert set(service.get("uses", [])) <= set(SERVICES), name


def test_every_variable_a_foundry_service_reads_is_declared_in_its_env():
    # azd substitutes ${VAR} in a connection or toolbox only when the service's own env declares it.
    for name in ["teamcenter", "technik-tools"]:
        service = dict(SERVICES[name])
        declared = set(service.pop("env", {}))
        used = set(re.findall(r"\$\{(\w+)\}", json.dumps(service)))
        assert used <= declared, f"{name}: {used - declared} not in env"


def test_the_agent_authenticates_to_the_server_as_itself():
    connection = SERVICES["teamcenter"]
    assert connection["authType"] == "AgenticIdentityToken"
    assert "credentials" not in connection  # no key or secret in the connection


def test_the_agent_service_reads_only_what_the_hosted_code_reads():
    agent = SERVICES["technik-agent"]
    hosted = (ROOT / "agent" / "hosted.py").read_text(encoding="utf-8")
    read = set(re.findall(r'os\.environ\["(\w+)"\]', hosted))
    # Foundry injects FOUNDRY_*; azure.yaml must not set it, and must set everything else the code reads.
    assert not any(key.startswith(("FOUNDRY_", "AGENT_")) for key in agent["env"])
    assert read - {"FOUNDRY_PROJECT_ENDPOINT"} <= set(agent["env"])
    assert agent["env"]["TOOLBOX_NAME"] in SERVICES and agent["toolboxes"] == [agent["env"]["TOOLBOX_NAME"]]
    deployments = [d["name"] for d in SERVICES["ai-project"]["deployments"]]
    assert agent["env"]["MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME"] in deployments


def test_the_container_app_runs_the_server_on_the_port_and_names_it_serves():
    bicep = (ROOT / "infra" / "server.bicep").read_text(encoding="utf-8")
    dockerfile = (ROOT / "server" / "Dockerfile").read_text(encoding="utf-8")
    assert "targetPort: 8000" in bicep and "EXPOSE 8000" in dockerfile and '"--http"' in dockerfile
    # Every environment variable the server reads is set, the key from Key Vault and never as a value.
    server = (ROOT / "server" / "teamcenter.py").read_text(encoding="utf-8")
    read = set(re.findall(r'os\.environ(?:\.get)?\[?\(?"(\w+)"', server)) - {"SNOWFLAKE_PRIVATE_KEY_FILE", "PORT"}
    set_in_bicep = set(re.findall(r"name: '(\w+)'", bicep))
    assert read <= set_in_bicep, read - set_in_bicep
    assert "{ name: 'SNOWFLAKE_PRIVATE_KEY', secretRef: 'snowflake-private-key' }" in bicep


def test_the_server_only_answers_callers_with_a_token_for_its_audience():
    base = (ROOT / "infra" / "base.bicep").read_text(encoding="utf-8")
    server = (ROOT / "infra" / "server.bicep").read_text(encoding="utf-8")
    assert "unauthenticatedClientAction: 'Return401'" in server
    assert "appRoleAssignmentRequired: true" in base
    audience = "'api://${tenant().tenantId}/technik-teamcenter-mcp'"
    assert f"var audience = {audience}" in base and f"var audience = {audience}" in server
