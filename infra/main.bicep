// infra/main.bicep — verify-dashboard altyapı önerisi (azure-prepare artifaktı)
// Hedef: Container Apps + Azure Files state-volume + ACR + Log Analytics
// Çalıştırma azure-deploy skill'i ile (plan Validated olduktan sonra) olur.
param name string = 'verify-dashboard'
param location string = resourceGroup().location

var tags = { 'azd-service-name': 'dashboard' }

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${name}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'env-${name}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'st${replace(name, '-', '')}'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
}

resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: 'dashboard-state'
  properties: { shareQuota: 5 }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: 'acr${replace(name, '-', '')}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'app-${name}'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
    }
    template: {
      containers: [
        {
          name: 'dashboard'
          image: 'REPLACE_WITH_ACR_IMAGE' // azure-deploy doldurur (azd build/push)
          resources: { cpu: json('1.0'), memory: '2Gi' }
          volumeMounts: [
            { volumeName: 'dashboard-state', mountPath: '/app/state' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
      volumes: [
        {
          name: 'dashboard-state'
          storageType: 'AzureFile'
          fileShares: [
            {
              shareName: fileShare.name
              storageAccountName: storage.name
              storageAccountKey: storage.listKeys().keys[0].value
            }
          ]
        }
      ]
    }
  }
}

output ACA_ENDPOINT string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output REGISTRY_LOGIN_SERVER string = acr.properties.loginServer
output ENVIRONMENT_ID string = containerEnv.id
