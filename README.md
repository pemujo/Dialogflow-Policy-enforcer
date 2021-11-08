# Dialogflow-Policy-enforcer
Used to enforce Dialogflow CX configuration policies:

1. Dialogflow CX Agent logging policy is to enable logs

Initiated by Google Cloud log sink with filter:

protoPayload.serviceName="dialogflow.googleapis.com" AND 
(protoPayload.methodName="google.cloud.dialogflow.v3alpha1.Webhooks.CreateWebhook" OR
protoPayload.methodName="google.cloud.dialogflow.v3alpha1.Webhooks.UpdateWebhook" OR 
protoPayload.request.agent.enableLogging="false" OR protoPayload.request.agent.enableStackdriverLogging="False")
