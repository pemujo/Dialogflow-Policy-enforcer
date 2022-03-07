
#!/bin/bash
# Create dialogflow-policy-enforcer topic, logging sink router and
# grant the required access
PROJECT_ID=$(gcloud config get-value project)

gcloud pubsub topics create dialogflow-policy-enforcer
gcloud logging sinks create dialogflow-policy-enforcer \
  pubsub.googleapis.com/projects/$PROJECT_ID/topics/dialogflow-policy-enforcer \
  --log-filter='
       protoPayload.authenticationInfo.principalEmail!="'"$PROJECT_ID"'@appspot.gserviceaccount.com"
       protoPayload.serviceName="dialogflow.googleapis.com" AND
       (Webhooks.CreateWebhook OR
       Webhooks.UpdateWebhook OR
       Agents.CreateAgent OR
       Agents.UpdateAgent OR
       Fulfillments.UpdateFulfillment
       )'

LOGGING_SERVICE_ACCOUNT=$(gcloud beta logging sinks describe dialogflow-policy-enforcer | sed -n  's/^writerIdentity: \(.*\)/\1/p')
echo "Granting roles/pubsub.publisher to $LOGGING_SERVICE_ACCOUNT"
gcloud alpha pubsub topics add-iam-policy-binding \
  projects/$PROJECT_ID/topics/dialogflow-policy-enforcer \
  --role roles/pubsub.publisher	 \
  --member $LOGGING_SERVICE_ACCOUNT
