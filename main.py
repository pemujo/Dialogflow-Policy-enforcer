# Copyright 2021 Google LLC
#
# This software is provided as-is, without warranty or representation for any
# use or purpose. Your use of it is subject to your agreement with Google.

import base64
import json
from google.cloud.dialogflowcx_v3.services.agents.client import AgentsClient
from google.cloud.dialogflowcx_v3.types.agent import UpdateAgentRequest
from google.cloud.dialogflowcx_v3.services.webhooks import WebhooksClient
from google.cloud.dialogflowcx_v3.types import UpdateWebhookRequest
from google.cloud.dialogflowcx_v3.types import AdvancedSettings
from google.api_core.client_options import ClientOptions
from google.protobuf import field_mask_pb2
from google.cloud.dialogflow_v2.services.fulfillments import FulfillmentsClient
from google.cloud.dialogflow_v2.types.fulfillment import UpdateFulfillmentRequest
from google.cloud.dialogflow_v2.services.agents import AgentsClient as AgentsClientES
from google.cloud.dialogflow_v2.types.agent import SetAgentRequest
from google.cloud.dialogflow_v2beta1.services.conversation_profiles import ConversationProfilesClient
from google.cloud.dialogflow_v2beta1.types.conversation_profile import UpdateConversationProfileRequest
# Placeholder for Dialogflow logging policy requirement.
log_policy = True


def main_function(event, context):
    """
    Triggered from a message on a Cloud Pub/Sub topic.
    Captures method and region from event['data']
    :param event:  Event payload
    :param context: Metadata for the event (google.cloud.functions.Context) Not used with this script
    """
    try:
        pubsub_message = base64.b64decode(event["data"]).decode("utf-8")
        pubsub_json = json.loads(pubsub_message)

        # Get event method and region
        log_method = pubsub_json["resource"]["labels"]["method"]
        region = pubsub_json["protoPayload"]["resourceLocation"]["currentLocations"][0]
        client_options = get_client_option(region)

        # Execute enforcing policies
        execute_policy_enforcer(log_method, client_options, pubsub_json)
        return "OK", 200

    except Exception:
        raise


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
        webhook_name = pubsub_json["protoPayload"]["resourceName"]
        webhook_updated = delete_webhook_credentials(webhook_name, client_options)
        print("Deleted static credentials on Webhook: " + str(webhook_name))
        return webhook_updated

    # Remove webhook credentials after a new Webhook is created
    elif "Webhooks.CreateWebhook" in log_method:
        agent_id = pubsub_json["protoPayload"]["resourceName"]
        enforced_webhooks = webhook_cred_enforcer(agent_id, client_options)
        for webhook in enforced_webhooks:
            print("Deleted static credentials on Webhook: " + str(webhook.name))
        return enforced_webhooks
    # Dialogflow ES Set correct log policy after agent is updated
    elif "Agents.UpdateAgentSettings" in log_method:
        agent_name = pubsub_json["protoPayload"]["resourceName"]
        agent_parts = agent_name.split('/')
        parent_name = f"{agent_parts[0]}/{agent_parts[1]}"
        enforce_agent_logging_es(parent_name, agent_name, log_policy, client_options)
    # Set correct log policy after agent is updated
    elif "Agents.UpdateAgent" in log_method:
        agent_id = pubsub_json["protoPayload"]["resourceName"]
        enforced_agent = enforce_agent_logging(agent_id, log_policy, client_options)
        print(
            "Updated Dialogflow log policy to "
            + str(log_policy)
            + " on Dialogflow agent: "
            + enforced_agent.name
        )
        return enforced_agent

    # Set correct log policy after agent is created
    elif "Agents.CreateAgent" in log_method:
        parent = pubsub_json["protoPayload"]["request"]["parent"]
        agents = list_agents(parent, client_options)
        enforced_agents = [
            enforce_agent_logging(agent.name, log_policy, client_options)
            for agent in agents
        ]
        for agent in enforced_agents:
            print(
                "Updated Dialogflow log policy "
                + str(log_policy)
                + " on Dialogflow Agent: "
                + agent.name
            )
        return enforced_agents
    # Dialogflow ES: Delete fulfillment static credentials
    elif "Fulfillments.UpdateFulfillment":
        fullfillment_name = pubsub_json["protoPayload"]["resourceName"]
        remove_fullfillment(client_options, fullfillment_name)
        print("Deleted static credentials on fullfillment: " + fullfillment_name)
    else:
        print("Nothing changed with log method received: " + log_method)
        return False


def get_client_option(region):
    """
    Dialogflow CX requires regional API endpoint based on the agent's region
    as per https://cloud.google.com/dialogflow/cx/docs/reference/rest/v3-overview#service-endpoint
    :param region: Agent's region
    :return: client_options object
    """
    # Regional options needed for CX
    if region == "global":
        region = ""
    else:
        region = region + "-"
    client_options = ClientOptions(api_endpoint=region + "dialogflow.googleapis.com")
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
    logging_settings = AdvancedSettings.LoggingSettings(
        enable_stackdriver_logging=policy, enable_interaction_logging=policy
    )
    agent_advanced_settings = AdvancedSettings(logging_settings=logging_settings)

    # Updates agent object with new logging settings
    agent.advanced_settings = agent_advanced_settings
    update_mask = field_mask_pb2.FieldMask(paths=["advanced_settings"])

    # Creates Dialogflow Agent update requests with the modified agent object and update_mask
    request = UpdateAgentRequest(agent=agent, update_mask=update_mask)

    # Submits Update Agent requests to Dialogflow API
    response = agents_client.update_agent(request=request)
    return response

def enforce_agent_logging_es(parent_name, agent_name, policy, client_options):
    """
    """
    agents_client = AgentsClientES(client_options=client_options)
    request = SetAgentRequest()
    request.agent.enable_logging = policy
    # Enable stackdriver logging is not allowed by public API
    request.agent.parent = parent_name
    request.update_mask = field_mask_pb2.FieldMask(
        paths=["enable_logging", ]
    )
    print(
        "Updated Dialogflow log policy "
        + str(log_policy)
        + " on Project: "
        + parent_name
    )
    agents_client.set_agent(request)

def delete_webhook_credentials(webhook_name, client_options):
    """
    Returns a webhook object after removing credentials
    :param webhook_name: Dialogflow Webhook name (str)
    :param client_options: API client options
    :return: webhook object
    """

    # Get Dialogflow Webhook API client
    webhook_client = WebhooksClient(client_options=client_options)

    # Get Webhook object
    webhook_object = webhook_client.get_webhook(name=webhook_name)

    # Update the fields to remove username and password.
    # TODO  It can include other html headers too
    update_mask = field_mask_pb2.FieldMask(
        paths=["generic_web_service.username", "generic_web_service.password"]
    )
    webhook_object.generic_web_service.username = ""
    webhook_object.generic_web_service.password = ""

    # Submit update request to Dialogflow API
    request = UpdateWebhookRequest(webhook=webhook_object, update_mask=update_mask)
    response = webhook_client.update_webhook(request=request)
    return response


def webhook_cred_enforcer(agent_id, client_options):
    """
    Removes static credentials from all webhooks of the agent_id
    :param agent_id: Dialogflow agent id (str)
    :param client_options: API client options
    :return: List of webhooks
    """

    webhook_client = WebhooksClient(client_options=client_options)
    webhooks = webhook_client.list_webhooks(parent=agent_id)
    modified_webhooks = [
        delete_webhook_credentials(webhook.name, client_options) for webhook in webhooks
    ]
    return modified_webhooks


def list_agents(parent, client_options):
    """
    Returns a ListAgentsPager object with the CX agents created on the project_id
    :param parent: Dialogflow agent location Format: projects/<Project ID>/locations/<Location ID> (str)
    :param client_options: API client options
    :return: List of Dialoglow agents
    """

    # Creates Dialogflow API Client
    agents_client = AgentsClient(client_options=client_options)

    # Gets  lists of agents on the GCP project
    agents_list = agents_client.list_agents(parent=parent)
    return agents_list

def remove_fullfillment(client_options, name):
    fullfillment_client = FulfillmentsClient(client_options=client_options)
    request = UpdateFulfillmentRequest()
    request.fulfillment.generic_web_service.username = ''
    request.fulfillment.generic_web_service.password = ''
    request.fulfillment.name = name
    request.update_mask = field_mask_pb2.FieldMask(
        paths=["generic_web_service.username", "generic_web_service.password"]
    )
    response = fullfillment_client.update_fulfillment(request)
    return response
