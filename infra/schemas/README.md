# Vendored azd schemas

Copies of the Azure Developer CLI's `azure.yaml` schema and the Foundry extension schemas it
composes, from [Azure/azure-dev](https://github.com/Azure/azure-dev) at commit
`c49286c2955a7ba5fc13487d960a723687651cc3` (MIT licence). The paths mirror that repository, so each
schema's `$id` resolves to its file here and `tests/test_deploy.py` validates `azure.yaml` with no
network. The Foundry extensions are in preview: refresh these when you raise `requiredVersions`.
