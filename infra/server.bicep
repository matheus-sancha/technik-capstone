// Stage 5, step 3: the MCP server on Azure Container Apps, behind Entra built-in authentication.
//   az deployment group create -g <your-resource-group> -f infra/server.bicep //     -p image=<registry>.azurecr.io/teamcenter-mcp:1 snowflakeAccount=<your-account>
// It finds what base.bicep created by name, so run that first in the same resource group.
extension graphV1

param location string = resourceGroup().location
param image string
param snowflakeAccount string

var name = 'teamcenter-mcp'
var suffix = uniqueString(resourceGroup().id)
var audience = 'api://${tenant().tenantId}/technik-teamcenter-mcp'

resource serverIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-teamcenter-mcp'
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: 'crtechnik${suffix}'
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: 'cae-technik-${suffix}'
}

resource serverApp 'Microsoft.Graph/applications@v1.0' existing = {
  uniqueName: 'technik-teamcenter-mcp-${suffix}'
}

var identityId = serverIdentity.id
var keyVaultName = 'kv-technik-${take(suffix, 10)}'

resource server 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      registries: [{ server: registry.properties.loginServer, identity: identityId }]
      secrets: [
        {
          // The agent's Snowflake key, read from the vault by the server's identity. Never in the image.
          name: 'snowflake-private-key'
          keyVaultUrl: 'https://${keyVaultName}${az.environment().suffixes.keyvaultDns}/secrets/snowflake-private-key'
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: name
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'SNOWFLAKE_ACCOUNT', value: snowflakeAccount }
            { name: 'SNOWFLAKE_USER', value: 'TECHNIK_AGENT_SVC' }
            { name: 'SNOWFLAKE_PRIVATE_KEY', secretRef: 'snowflake-private-key' }
            { name: 'SNOWFLAKE_ROLE', value: 'TECHNIK_AGENT_RO' }
            { name: 'SNOWFLAKE_WAREHOUSE', value: 'TECHNIK_AGENT_WH' }
            { name: 'SNOWFLAKE_DATABASE', value: 'TECHNIK_DW' }
            { name: 'SNOWFLAKE_SCHEMA', value: 'OPS' }
            { name: 'MCP_ALLOWED_HOSTS', value: '${name}.${environment.properties.defaultDomain}' }
          ]
        }
      ]
      // Stateless streamable HTTP, so any replica can take any request.
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}

// No token for the server's audience, no request: Container Apps answers 401 before the code runs.
resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = {
  parent: server
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: { unauthenticatedClientAction: 'Return401' }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: serverApp.appId
          openIdIssuer: '${az.environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
        validation: { allowedAudiences: [audience, serverApp.appId] }
      }
    }
  }
}

output url string = 'https://${server.properties.configuration.ingress.fqdn}/mcp'
