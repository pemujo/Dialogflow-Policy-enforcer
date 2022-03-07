#!/bin/bash
# Deploy main_function cloud function and attach it to
# dialogflow-policy-enforcer topic
PROJECT_ID=$(gcloud config get-value project)

gcloud functions deploy dialogflow-policy-enforcer --entry-point main_function  --runtime python39 --trigger-topic dialogflow-policy-enforcer
