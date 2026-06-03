@description('Location for all resources')
param location string = resourceGroup().location

@description('Location for Static Web App (subset of regions support the Free SKU)')
param swaLocation string = 'eastus2'

@description('Location for App Service Plan + Function App (needs Y1 Consumption quota)')
param functionLocation string = 'westus2'

@description('Unique suffix to avoid name collisions')
param suffix string = uniqueString(resourceGroup().id)

@description('API-Sports API key')
@secure()
param apiSportsKey string

@description('Anthropic API key')
@secure()
param anthropicKey string

@description('football-data.org API key')
@secure()
param footballDataKey string

@description('SerpAPI key for search news')
@secure()
param serpaKey string

// ---------------------------------------------------------------------------
// Storage Account (required by Azure Functions)
// ---------------------------------------------------------------------------
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'stwc2026${suffix}'
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource predictQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = {
  parent: queueService
  name: 'predict-trigger'
}

// ---------------------------------------------------------------------------
// Cosmos DB — NoSQL API, permanent free tier
// ---------------------------------------------------------------------------
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' = {
  name: 'cosmos-wc2026-${suffix}'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    enableFreeTier: true
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0 }]
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosAccount
  name: 'wc2026'
  properties: {
    resource: { id: 'wc2026' }
    options: { throughput: 400 }
  }
}

resource teamsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cosmosDatabase
  name: 'teams'
  properties: {
    resource: {
      id: 'teams'
      partitionKey: { paths: ['/group'], kind: 'Hash' }
    }
  }
}

resource fixturesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cosmosDatabase
  name: 'fixtures'
  properties: {
    resource: {
      id: 'fixtures'
      partitionKey: { paths: ['/matchday'], kind: 'Hash' }
    }
  }
}

resource predictionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cosmosDatabase
  name: 'predictions'
  properties: {
    resource: {
      id: 'predictions'
      partitionKey: { paths: ['/matchday'], kind: 'Hash' }
    }
  }
}

resource scoresContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cosmosDatabase
  name: 'scores'
  properties: {
    resource: {
      id: 'scores'
      partitionKey: { paths: ['/matchday'], kind: 'Hash' }
    }
  }
}

// ---------------------------------------------------------------------------
// Key Vault
// ---------------------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-wc2026-${suffix}'
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
    enableSoftDelete: true
  }
}

resource secretApiSports 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'apisports-api-key'
  properties: { value: apiSportsKey }
}

resource secretAnthropic 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'anthropic-api-key'
  properties: { value: anthropicKey }
}

resource secretFootballData 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'football-data-api-key'
  properties: { value: footballDataKey }
}

resource secretSerpa 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'serpa-api-key'
  properties: { value: serpaKey }
}

resource secretCosmos 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cosmos-connection-string'
  properties: {
    value: cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString
  }
}

// ---------------------------------------------------------------------------
// App Service Plan (Consumption / Serverless)
// ---------------------------------------------------------------------------
resource hostingPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'plan-wc2026-${suffix}'
  location: functionLocation
  sku: { name: 'Y1', tier: 'Dynamic' }
  kind: 'linux'
  properties: { reserved: true }  // required for Linux Consumption plan
}

// ---------------------------------------------------------------------------
// Function App
// ---------------------------------------------------------------------------
resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: 'func-wc2026-${suffix}'
  location: functionLocation
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: hostingPlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=core.windows.net'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'KEY_VAULT_URI'
          value: keyVault.properties.vaultUri
        }
        {
          name: 'COSMOS_DATABASE_NAME'
          value: 'wc2026'
        }
        {
          name: 'PREDICT_QUEUE_NAME'
          value: 'predict-trigger'
        }
        {
          name: 'CosmosDbConnectionString'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/cosmos-connection-string/)'
        }
        {
          name: 'APISPORTS_API_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/apisports-api-key/)'
        }
        {
          name: 'ANTHROPIC_API_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/anthropic-api-key/)'
        }
        {
          name: 'FOOTBALL_DATA_API_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/football-data-api-key/)'
        }
        {
          name: 'SERPA_API_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/serpa-api-key/)'
        }
      ]
    }
  }
}

// Grant Function App managed identity the Key Vault Secrets User role
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, functionApp.id, kvSecretsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Static Web App
// ---------------------------------------------------------------------------
resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: 'swa-wc2026-${suffix}'
  location: swaLocation
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
output functionAppName string = functionApp.name
output staticWebAppName string = staticWebApp.name
output keyVaultUri string = keyVault.properties.vaultUri
output cosmosDatabaseName string = cosmosDatabase.name
