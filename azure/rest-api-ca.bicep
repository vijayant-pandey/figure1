@description('Specifies the location for resources.')
param location string = resourceGroup().location

@description('Full resource ID of the container app environment')
param environmentId string = '/subscriptions/74dddba2-2caa-4f56-9cc6-3d64c3a76e40/resourceGroups/microservices-rg/providers/Microsoft.App/managedEnvironments/microservices-cae'

@secure()
param firebaseKey string

@secure()
param jwtSecretKey string

@secure()
param dbPassword string

@secure()
param elasticsearchKey string

@secure()
param awsSecretKey string

@secure()
param containerRegistryPassword string

var envVariables = loadJsonContent('./env-variables.json')

resource restApiCA 'Microsoft.App/containerApps@2023-04-01-preview' = {
  name: 'rest-api-ca'
  location: location
  properties: {
    environmentId: environmentId
    configuration: {
      secrets: [
        {
          name: 'firebase-key'
          value: firebaseKey
        }
        {
          name: 'jwt-secret-key'
          value: jwtSecretKey
        }
        {
          name: 'db-password'
          value: dbPassword
        }
        {
          name: 'elasticsearch-key'
          value: elasticsearchKey
        }
        {
          name: 'ctr-reg-password'
          value: containerRegistryPassword
        }
        {
          name: 'aws-secret-key'
          value: awsSecretKey
        }
      ]
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 30000
        exposedPort: 0
        transport: 'Auto'
        allowInsecure: false
      }
      registries: [
        {
          server: 'fig1cr.azurecr.io'
          username: 'fig1cr'
          passwordSecretRef: 'ctr-reg-password'
        }
      ]
    }
    template: {
      containers: [
        {
          image: 'fig1cr.azurecr.io/backend:dev-202308221733'
          // image: 'fig1cr.azurecr.io/backend:sqla'
          name: 'rest-api'
          command: [
            'gunicorn'
          ]
          env: envVariables
          resources: {
            cpu: 1
            memory: '2Gi'
          }
          probes: []
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 10
      }
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
}
