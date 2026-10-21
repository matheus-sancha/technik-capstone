// Stage 5, step 1: everything the MCP server needs before it can run.
//   az deployment group create -g <your-resource-group> -f infra/base.bicep
// Then put the agent's Snowflake key in the vault and build the image (README, "Ship it").
extension graphV1

param location string = resourceGroup().location

var suffix = uniqueString(resourceGroup().id)
var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-technik-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// The hosted agent's traces land here once you connect it to the Foundry project (README, step 7).
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-technik-${suffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// The server's identity: it reads the key from the vault and pulls its image, nothing else.
resource serverIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-teamcenter-mcp'
  location: location
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-technik-${take(suffix, 10)}'
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
  }
}

resource readSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, serverIdentity.id, keyVaultSecretsUser)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUser)
    principalId: serverIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crtechnik${suffix}'
  location: location
  sku: { name: 'Basic' }
}

resource pullImages 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, serverIdentity.id, acrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
    principalId: serverIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-technik-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// The server's Entra app: the audience its tokens are for, and the one role a caller must hold.
var audience = 'api://${tenant().tenantId}/technik-teamcenter-mcp'
var readRole = guid(resourceGroup().id, 'Teamcenter.Read')

resource serverApp 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: 'technik-teamcenter-mcp-${suffix}'
  displayName: 'Technik Teamcenter MCP server'
  signInAudience: 'AzureADMyOrg'
  identifierUris: [audience]
  api: { requestedAccessTokenVersion: 2 }
  appRoles: [
    {
      id: readRole
      value: 'Teamcenter.Read'
      displayName: 'Read Teamcenter'
      description: 'Call the read-only Teamcenter tools.'
      allowedMemberTypes: ['Application']
      isEnabled: true
    }
  ]
}

// Assignment required: Entra issues a token only to an identity that holds Teamcenter.Read.
resource serverPrincipal 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: serverApp.appId
  appRoleAssignmentRequired: true
}

output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output keyVaultName string = vault.name
output serverPrincipalId string = serverPrincipal.id
output readRoleId string = readRole
output audience string = audience
