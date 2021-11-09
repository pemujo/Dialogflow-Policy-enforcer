import base64
import json
from google.cloud.dialogflowcx_v3.services.agents.client import AgentsClient
from google.cloud.dialogflowcx_v3.types.agent import UpdateAgentRequest
from google.cloud.dialogflowcx_v3.services.webhooks import WebhooksClient
from google.cloud.dialogflowcx_v3.types import UpdateWebhookRequest
from google.cloud.dialogflowcx_v3.types import AdvancedSettings
from google.api_core.client_options import ClientOptions
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
    region = pubsub_json['protoPayload']['resourceLocation']['currentLocations'][0]

    # Remove webhook credentials after an update
    if log_method == "google.cloud.dialogflow.v3alpha1.Webhooks.UpdateWebhook":
        webhook_name = pubsub_json['protoPayload']['resourceName']
        delete_webhook_credentials(webhook_name)
        print('Deleted static credentials on Webhook: ' + str(webhook_name) + 'inform end user')


    # Remove webhook credentials after a Webhook is created
    elif log_method == "google.cloud.dialogflow.v3alpha1.Webhooks.CreateWebhook":
        agent_id = pubsub_json['protoPayload']['resourceName']
        enforced_webhooks = webhook_cred_enforcer(agent_id, region)
        for webhook in enforced_webhooks:
            print('Deleted static credentials on Webhook: ' + str(webhook.name))

    # Set correct log policy after agent is created
    elif log_method == "google.cloud.dialogflow.v3alpha1.Agents.CreateAgent":
        parent = pubsub_json['protoPayload']['request']['parent']
        agents = list_agents(parent, region)
        enforced_agents = [enforce_agent_logging(agent.name, log_policy, region) for agent in agents]
        print('Updated Dialogflow log policy to ' + str(log_policy) + ' on Dialogflow agents:')
        for agent in enforced_agents:
            print('Agent: ' + agent.name)

    # Set correct log policy after agent is updated
    elif log_method == "google.cloud.dialogflow.v3alpha1.Agents.UpdateAgent":
        agent_id = pubsub_json['protoPayload']['resourceName']
        enforced_agent = enforce_agent_logging(agent_id, log_policy, region)
        print('Updated Dialogflow log policy to ' + str(log_policy) + ' on Dialogflow agent: ' + enforced_agent.name)

    else:
        print(log_method)
        print('No logs matched. Nothing changed')


def get_client_option(region):
    """
    Dialogflow CX requires regional API endpoint based on the agent's region
    as per https://cloud.google.com/dialogflow/cx/docs/reference/rest/v3-overview#service-endpoint
    :param region: Agent's region
    :return: client_options object
    """
    # Regional options needed for CX
    if region == 'global':
        region = ''
    else:
        region = region + '-'
    client_options = ClientOptions(api_endpoint=region + 'dialogflow.googleapis.com')
    return client_options


def enforce_agent_logging(name, policy, region):
    """
    Used to enforce the logging policy on the agent.
    :param name: Dialogflow Agent ID (str)
    :param policy: Dialogflow Logging policy required (bool)
    :param region: Dialogflow Agent's region (str)
    :return: agent object with modified logging settings
    """

    # Regional options needed for CX
    client_options = get_client_option(region)

    # Creates Dialogflow API Client
    agents_client = AgentsClient(client_options=client_options)

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


def delete_webhook_credentials(webhook_name, region):
    """ Returns a webhook object without credentials
    Args:
        webhook_name (str): Dialogflow Webhook
        :param region:
    """
    # Regional options needed for CX
    client_options = get_client_option(region)

    # Get Dialogflow Webhook API client
    webhook_client = WebhooksClient(client_options=client_options)

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
    enforced_logging_agents = [enforce_agent_logging(agent.name, log_policy) for agent in failed_policy_agents]
    return enforced_logging_agents


def webhook_cred_enforcer(agent_id, region):
    """ Removes static credentials from all webhooks of the agent_id
    Args:
         agent_id (str): Dialogflow agent id

    """
    # Regional options needed for CX
    client_options = get_client_option(region)

    webhook_client = WebhooksClient(client_options=client_options)
    webhooks = webhook_client.list_webhooks(parent=agent_id)
    modified_webhooks = [delete_webhook_credentials(webhook.name, region) for webhook in webhooks]
    return modified_webhooks


def list_agents(parent, region):
    """ Returns a ListAgentsPager object with the CX agents created on the project_id
    Args:
        parent (str): Dialogflow agent location Format: projects/<Project ID>/locations/<Location ID>
        region (str): Agent's Google Cloud region
    """

    # Regional options needed for CX
    client_options = get_client_option(region)

    # Creates Dialogflow API Client
    agents_client = AgentsClient(client_options=client_options)

    agents_list = agents_client.list_agents(parent=parent)
    return agents_list
