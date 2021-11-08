import base64
import json
from google.cloud.dialogflowcx_v3.services.agents.client import AgentsClient
from google.cloud.dialogflowcx_v3.types.agent import UpdateAgentRequest
from google.cloud.dialogflowcx_v3.services.webhooks import WebhooksClient
from google.cloud.dialogflowcx_v3.types import UpdateWebhookRequest
from google.cloud.dialogflowcx_v3.types import AdvancedSettings
from google.protobuf import field_mask_pb2

# Placeholder for Dialogflow logging policy requirement.
log_policy = True


def identify_log_message(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic. Executes functions based on the log's 'Method'
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    # Decode Data from event and capture log method from ['data']['resource']['labels']['method']
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    pubsub_json = json.loads(pubsub_message)
    log_method = pubsub_json['resource']['labels']['method']

    # Execute Webhook function to remove credentials
    if log_method == "google.cloud.dialogflow.v3alpha1.Webhooks.UpdateWebhook":
        webhook_name = pubsub_json['protoPayload']['resourceName']
        delete_webhook_credentials(webhook_name)
        print('Deleted static credentials on Webhook: ' + str(webhook_name) + 'inform end user')

    elif log_method == "google.cloud.dialogflow.v3alpha1.Webhooks.CreateWebhook":
        agent_id = pubsub_json['protoPayload']['resourceName']
        enforced_webhooks = webhook_cred_enforcer(agent_id)
        for webhook in enforced_webhooks:
            print('Deleted static credentials on Webhook: ' + str(webhook.name))

    # Execute Agent logging function to set correct log policy
    elif log_method == "google.cloud.dialogflow.v3alpha1.Agents.CreateAgent":

        parent = pubsub_json['protoPayload']['request']['parent']
        agents = list_agents(parent)
        enforced_agents = [enforce_agent_logging(agent.name, log_policy) for agent in agents]
        print('Updated Dialogflow log policy to ' + str(log_policy) + ' on Dialogflow agent: ' + enforced_agents)


    elif log_method == "google.cloud.dialogflow.v3alpha1.Agents.UpdateAgent":
        agent_id = pubsub_json['protoPayload']['resourceName']
        enforced_agent = enforce_agent_logging(agent_id, log_policy)
        print('Updated Dialogflow log policy to ' + str(log_policy) + ' on Dialogflow agent: ' + enforced_agent.name)


    else:
        print(log_method)
        print('No logs matched. Nothing changed')


def enforce_agent_logging(name, policy):
    """ Returns an agent object with modified logging settings
    Args:
        name (str): Dialogflow Agent ID
        policy (bool): Dialogflow Logging policy required
    """
    # Creates Dialogflow API Client
    agents_client = AgentsClient()

    # Gets Dialogflow agent object
    agent = agents_client.get_agent(name=name)

    # Builds agent advanced settings  based on logging policy
    logging_settings = AdvancedSettings.LoggingSettings(enable_stackdriver_logging=policy,
                                                        enable_interaction_logging=policy)
    agent_advanced_settings = AdvancedSettings(logging_settings=logging_settings)

    # Updates agent object with new logging settings
    agent.advanced_settings = agent_advanced_settings
    update_mask = field_mask_pb2.FieldMask(paths=["advanced_settings"])

    # Creates Dialogflow Agent update requests with the modified agent object and update_mask
    request = UpdateAgentRequest(agent=agent, update_mask=update_mask)

    # Submits Update Agent requests to Dialogflow API
    response = agents_client.update_agent(request=request)
    return response


def delete_webhook_credentials(webhook_name):
    """ Returns a webhook object without credentials
    Args:
        webhook_name (str): Dialogflow Webhook
    """

    # Get Dialogflow Webhook API client
    webhook_client = WebhooksClient()

    # Get Webhook object
    webhook_object = webhook_client.get_webhook(name=webhook_name)

    # Update the fields to remove username and password
    update_mask = field_mask_pb2.FieldMask(paths=["generic_web_service.username", "generic_web_service.password"])
    webhook_object.generic_web_service.username = ''
    webhook_object.generic_web_service.password = ''

    # Submit update request to Dialogflow API
    request = UpdateWebhookRequest(webhook=webhook_object, update_mask=update_mask)
    response = webhook_client.update_webhook(request=request)
    return response


def log_policy_check(agents_list):
    incorrect_log_agents = [agent for agent in agents_list if
                            agent.advanced_settings.logging_settings.enable_stackdriver_logging != log_policy]
    return incorrect_log_agents


def log_policy_enforcer(agents_list):
    failed_policy_agents = log_policy_check(agents_list)
    enabled_logging = [enforce_agent_logging(agent.name, log_policy) for agent in failed_policy_agents]
    return enabled_logging


def webhook_cred_enforcer(agent_id):
    """ Removes static credentials from all webhooks of the agent_id
    Args:
         agent_id (str): Dialogflow agent id

    """
    webhook_client = WebhooksClient()
    webhooks = webhook_client.list_webhooks(parent=agent_id)
    modified_webhooks = [delete_webhook_credentials(webhook.name) for webhook in webhooks]
    return modified_webhooks


def list_agents(parent):
    """ Returns a ListAgentsPager object with the CX agents created on the project_id
    Args:
        project_id (str): Google Cloud Project ID
    """
    # Creates Dialogflow API Client
    agents_client = AgentsClient()

    agents_list = agents_client.list_agents(parent=parent)
    return agents_list
