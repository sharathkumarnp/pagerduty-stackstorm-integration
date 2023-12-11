# Pagerduty integration with stackstorm
This is a sample test process to understand how to integrate the pagerdurty to stackstorm

This code is a Python script designed to interact with a Kubernetes cluster and perform various operations on pods and nodes. It's part of an automation workflow, likely intended to be used in conjunction with Kubernetes and the StackStorm automation platform. Here's a breakdown of the code:

# Import Statements:

The code starts with import statements, bringing in the necessary Python modules and Kubernetes client libraries, including multiprocessing, subprocess, json, time, and kubernetes.

# Mapping of AWS Regions and Clusters:
The script defines two dictionaries that map AWS regions to primary Kubernetes clusters and primary clusters to their subclusters. These mappings are used to determine the target cluster based on the AWS region provided.

# EC2Action Class:
The core functionality of the script is encapsulated in a Python class called EC2Action. This class appears to be designed as a custom action for StackStorm, an open-source automation platform. It contains methods for performing specific tasks.

# run Method:
The run method is the entry point for the script and is expected to be executed when this action is triggered in a StackStorm workflow. It takes two arguments: region_name (the AWS region) and instance_id (an AWS instance ID). The purpose of this method is to locate the AWS instance within the associated Kubernetes clusters based on the provided region and instance ID.

# Helper Methods:
The EC2Action class includes several helper methods to perform specific tasks:

* **_find_instance_id_in_subclusters:_** Searches for the EC2 instance in subclusters when not found in the primary cluster.


* _**find_node_and_cordon:**_ Uses kubectl to find the node where the EC2 instance is running and marks it as unschedulable.


* **_cordon_node:_** Marks a Kubernetes node as unschedulable and restarts related pods.


* **_sts_name:_** Determines the StatefulSet name for pods related to Artifactory or Xray.


* **_scale_and_restart:_** Scales and restarts a StatefulSet in a specified namespace.


* **_restart_pod:_** Deletes a pod to trigger a restart.

# Multiprocessing:
The code employs the multiprocessing module to parallelize certain operations, such as scaling and restarting StatefulSets and restarting pods. This can help improve the efficiency of the script when dealing with multiple pods.


# Notes:

1. This script is designed for a specific use case and is expected to run in an environment with the necessary Kubernetes and StackStorm configurations.

2. Error handling is present in the code to catch exceptions and provide error messages.

3. The script performs operations on Kubernetes clusters, so it should be run with the appropriate permissions and access to the clusters.

4. The script is primarily focused on managing StatefulSets and pods within a Kubernetes cluster and is designed for specific scenarios where scaling and restarting are needed.

5. The script includes print statements for logging and debugging purposes. In a production environment, you might want to use proper logging mechanisms.

6. The script assumes that you have the kubectl command-line tool configured on the machine where it's running.

If you have specific questions or need further details about any part of the code, please let me know.

#### **For Further reference I've included a test python file which helps to run directly over your local bash terminal**