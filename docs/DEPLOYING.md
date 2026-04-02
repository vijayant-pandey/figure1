## Account Requirements

1. Add the `Healthcare NLP Service Viewer` role to the `firebase-adminsdk` principal in IAM. This is required for the mesh terms auto-tagging.
2. Enable the Cloud Translation API at https://console.developers.google.com/apis/api/translate.googleapis.com/overview?project=`project_id`.
3. Create an AWS IAM user and grant it the environment role, e.g., `pro-dev-S3`. This is required to support image uploads on the client app. Create an access key and set the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` env vars.

## Deploying with Bicep

```bash
# deploy celery workers
az deployment group create --resource-group celery-rg --template-file celery-workers-ca.bicep --parameters celery-workers-ca.secure.bicepparam

# deploy celery beat
az deployment group create --resource-group celery-rg --template-file celery-beat-ca.bicep --parameters celery-beat-ca.secure.bicepparam

# deploy rest api
az deployment group create --resource-group rest-api-rg --template-file rest-api-ca.bicep --parameters rest-api-ca.secure.bicepparam

# deploy flower
az deployment group create --resource-group celery-rg --template-file celery-flower-ca.bicep --parameters celery-flower-ca.secure.bicepparam

```
