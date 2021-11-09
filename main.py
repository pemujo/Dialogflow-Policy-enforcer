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


def main_function(event, context):
    """
    Triggered from a message on a Cloud Pub/Sub topic.
    Captures method, region from event['data']['resource']['labels']['method']
    :param event:  Event payload (dict)
    :param context: Metadata for the event (google.cloud.functions.Context) Not used with this script
    :return:
    """

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    pubsub_json = json.loads(pubsub_message)

    # Get event method and region
    log_method = pubsub_json['resource']['labels']['method']
    region = pubsub_json['protoPayload']['resourceLocation']['currentLocations'][0]
    client_options = get_client_option(region)
    execute_policy_enforcer(log_method, client_options, pubsub_json)


def execute_policy_enforcer(log_method, client_options, pubsub_json):
    """
    Executes functions based on the log's 'Method'
    :param log_method: Log's method captured (str)
    :param client_options: API client options (client_options)
    :param pubsub_json: JSON including the pub/sub message (dict)
    :return: Modified object based on the log's method
    """

    # Remove webhook credentials after an update
    if "Webhooks.UpdateWebhook" in log_method:
        webhook_name = pubsub_json['protoPayload']['resourceName']
        webhook_updated = delete_webhook_credentials(webhook_name, client_options)
        print('Deleted static credentials on Webhook: ' + str(webhook_name))
        return webhook_updated

    # Remove webhook credentials after a new Webhook is created
    elif "Webhooks.CreateWebhook" in log_method:
        agent_id = pubsub_json['protoPayload']['resourceName']
        enforced_webhooks = webhook_cred_enforcer(agent_id, client_options)
        for webhook in enforced_webhooks:
            print('Deleted static credentials on Webhook: ' + str(webhook.name))
        return enforced_webhooks

    # Set correct log policy after agent is updated
    elif "Agents.UpdateAgent" in log_method:
        agent_id = pubsub_json['protoPayload']['resourceName']
        enforced_agent = enforce_agent_logging(agent_id, log_policy, client_options)
        print('Updated Dialogflow log policy to ' + str(log_policy) + ' on Dialogflow agent: ' + enforced_agent.name)
        return enforced_agent

    # Set correct log policy after agent is created
    elif "Agents.CreateAgent" in log_method:
        parent = pubsub_json['protoPayload']['request']['parent']
        agents = list_agents(parent, client_options)
        enforced_agents = [enforce_agent_logging(agent.name, log_policy, client_options) for agent in agents]
        for agent in enforced_agents:
            print('Updated Dialogflow log policy ' + str(log_policy) + ' on Dialogflow Agent: ' + agent.name)
        return enforced_agents

    else:
        print(log_method)
        print('No logs matched. Nothing changed')
        return False


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


def enforce_agent_logging(name, policy, client_options):
    """
    Used to enforce the logging policy on the agent.
    :param client_options: API client options
    :param name: Dialogflow Agent ID (str)
    :param policy: Dialogflow Logging policy required (bool)
    :return: agent object with modified logging settings
    """

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


def delete_webhook_credentials(webhook_name, client_options):
    """ Returns a webhook object without credentials
    Args:
        :param client_options: API client options
        :param webhook_name: Dialogflow Webhook name (str)
    """

    # Get Dialogflow Webhook API client
    webhook_client = WebhooksClient(client_options=client_options)

    # Get Webhook object
    webhook_object = webhook_client.get_webhook(name=webhook_name)

    # Update the fields to remove username and password.
    # TODO  It can include other html headers too
    update_mask = field_mask_pb2.FieldMask(paths=["generic_web_service.username", "generic_web_service.password"])
    webhook_object.generic_web_service.username = ''
    webhook_object.generic_web_service.password = ''

    # Submit update request to Dialogflow API
    request = UpdateWebhookRequest(webhook=webhook_object, update_mask=update_mask)
    response = webhook_client.update_webhook(request=request)
    return response


def webhook_cred_enforcer(agent_id, client_options):
    """ Removes static credentials from all webhooks of the agent_id
    Args:
         :param agent_id: Dialogflow agent id (str):
         :param client_options: API client options

    """
    webhook_client = WebhooksClient(client_options=client_options)
    webhooks = webhook_client.list_webhooks(parent=agent_id)
    modified_webhooks = [delete_webhook_credentials(webhook.name, client_options) for webhook in webhooks]
    return modified_webhooks


def list_agents(parent, client_options):
    """ Returns a ListAgentsPager object with the CX agents created on the project_id
    Args:
        :param parent: Dialogflow agent location Format: projects/<Project ID>/locations/<Location ID> (str)
        :param client_options: API client options
    """

    # Creates Dialogflow API Client
    agents_client = AgentsClient(client_options=client_options)

    agents_list = agents_client.list_agents(parent=parent)
    return agents_list
