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
param containerRegistryPassword string

@secure()
param awsSecretKey string

var envVariables = loadJsonContent('./env-variables.json')

resource celeryBeatCA 'Microsoft.App/containerApps@2023-04-01-preview' = {
  name: 'celery-beat-ca'
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
      registries: [
        {
          server: 'fig1cr.azurecr.io'
          username: 'fig1cr'
          passwordSecretRef: 'ctr-reg-password'
          identity: ''
        }
      ]
    }
    template: {
      containers: [
        {
          image: 'fig1cr.azurecr.io/backend:dev-202308221733'
          name: 'celery-beat'
          command: [
            'celery'
          ]
          args: [ '-A', 'figure1', 'beat' ]
          env: envVariables
          resources: {
            #disable-next-line BCP036
            cpu: '0.25'
            memory: '0.5Gi'
          }
          probes: []
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  identity: {
    type: 'None'
  }
}
