# Stackstorm Functions
StackStorm allows you to define rules that specify conditions for triggering actions in response to certain events. Let's break down the components of this rule configuration:

# Rule Definition:

name: The name of the rule. In this case, it is named "st2-rules-ec2-retirement-trigger."
pack: The StackStorm pack where this rule is defined. In this case, it is in the "pd" pack.
description: A brief description of the rule's purpose. It is described as a "Rule for Ec2 retirement."
enabled: Specifies whether the rule is enabled (set to true) or disabled (set to false).
# Trigger Configuration:

The trigger section defines the type of event or trigger that will activate this rule.
type: The type of the trigger. In this case, it is "core.st2.webhook," which typically means that the rule will be triggered by an incoming webhook request.
parameters: Additional parameters related to the trigger. It includes a URL parameter pointing to the webhook URL that will trigger this rule.
# Criteria:

The criteria section defines the conditions that must be met for the rule to trigger an action.
trigger.body.summary: This is a reference to an attribute in the body of the trigger event. It checks the "summary" field.
type: Specifies the type of condition to apply. In this case, it is "contains," which checks if the text contains a certain pattern.
pattern: The specific pattern that the "summary" field should contain for the rule to trigger.
# Action Configuration:

The action section specifies what action should be taken when the criteria are met.
ref: The reference to the action to be executed. It references "pd.st2-actions-ec2-retirement-trigger," which is likely the name of an action defined in the "pd" pack.
parameters: Additional parameters to pass to the action. In this case, it includes an "incident_id" parameter, which is populated with data from the trigger event using Jinja2 templating. The value is taken from the trigger body's "__pd_metadata.incident.id" field.
In summary, this rule is designed to be triggered by a webhook event of type "core.st2.webhook." It checks the "summary" field of the incoming webhook data, and if it contains the word "Retirement," it triggers the specified action with the provided parameters, including the incident ID extracted from the trigger data.

This rule is a part of an automation workflow and allows you to automate responses to specific events or conditions, such as handling EC2 instance retirements based on incoming webhook triggers. The action associated with this rule, "pd.st2-actions-ec2-retirement-trigger," would define what actions should be taken in response to the retirement event.

# "Action Chain" 
A workflow that allows you to define a sequence of actions that should be executed in a specific order. Action Chains are useful for orchestrating complex processes and automating multi-step tasks. In your provided YAML configuration, you have defined an Action Chain named "st2-actions-ec2-retirement-trigger" in the "pd" pack. Let's break down the components of this Action Chain configuration:

# Action Chain Definition:

name: The name of the Action Chain. It is named "st2-actions-ec2-retirement-trigger."
description: A brief description of the Action Chain's purpose. It is described as a "Simple Action Chain workflow for ec2 retirement alert."
pack: The StackStorm pack where this Action Chain is defined. In this case, it is in the "pd" pack.
runner_type: Specifies the type of runner for this Action Chain. Here, it is set to "action-chain," indicating that this is an Action Chain workflow.
entry_point: The entry point for the Action Chain, which is specified as "chains/st2-chains-ec2-retirement-trigger.yaml." This points to the file that contains the detailed definition of the chain.
Enabled and Parameters:

enabled: Specifies whether the Action Chain is enabled (set to true) or disabled (set to false).
parameters: This section defines the input parameters that the Action Chain expects when it is triggered. In this case, it expects an "incident_id," which is of type string and is marked as required. The "incident_id" parameter is used to pass data into the Action Chain when it is executed.