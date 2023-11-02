import multiprocessing
import subprocess
import json
import time
from st2common.runners.base_action import Action
from kubernetes import client, config

# Define a mapping of AWS regions to primary clusters
region_to_primary_cluster = {
    "us-east-1": "prod-use1",
    "us-west-1": "prod-usw1",
    # Add more if you have any regions
}

# Define a mapping of primary clusters to their subclusters
primary_to_subclusters = {
    "prod-use1": ["prod-2-use1", "prod-3-use1", "prod-4-use1"],
    # Add if you have any sub-regions under the primary
}

class EC2Action(Action):
    def run(self, region_name: str, instance_id: str):
        # Load Kubernetes configuration
        config.load_kube_config()
        try:
            if region_name in region_to_primary_cluster:
                primary_cluster_name = region_to_primary_cluster[region_name]

                # Iterate through subclusters if any
                if primary_cluster_name in primary_to_subclusters:
                    subclusters = primary_to_subclusters[primary_cluster_name]
                    for subcluster_name in subclusters:
                        self.find_node_in_cluster(region_name, instance_id, subcluster_name)
            else:
                print(f"Region {region_name} is not in the mapping. Unable to search for instance ID.")
        except Exception as e:
            print(f"Error: {e}")

    def get_statefulset_name(self, pod_name, namespace):
        try:
            # Run the kubectl describe command and use grep to extract the StatefulSet name
            describe_output = subprocess.check_output(
                ["kubectl", "describe", "pod", pod_name, "-n", namespace], universal_newlines=True
            )
            controlled_by_line = [
                line for line in describe_output.split("\n") if "Controlled By: StatefulSet/" in line
            ]
            if controlled_by_line:
                statefulset_name = controlled_by_line[0].split("Controlled By: StatefulSet/")[1].strip()
                return statefulset_name
            else:
                return None
        except Exception as e:
            print(f"Error extracting StatefulSet name for pod {pod_name} in namespace {namespace}: {e}")
            return None

    def get_original_replicas(self, sts_name, namespace):
        try:
            api_instance = client.AppsV1Api()

            # Get the StatefulSet object
            statefulset = api_instance.read_namespaced_stateful_set(sts_name, namespace)

            # Retrieve the original replica count from the StatefulSet's specification
            original_replicas = statefulset.spec.replicas

            return original_replicas
        except Exception as e:
            print(f"Error retrieving original replicas: {e}")
            return None

    def find_node_in_cluster(self, region_name, instance_id, cluster_name):
        try:
            v1 = client.CoreV1Api()

            # Search for instance ID in annotations of nodes within the cluster
            nodes = v1.list_node().items
            for node in nodes:
                node_name = node.metadata.name
                annotations = node.metadata.annotations or {}
                node_id_annotation = annotations.get("csi.volume.kubernetes.io/nodeid", "")

                try:
                    node_instance_id = json.loads(node_id_annotation)["ebs.csi.aws.com"]
                    if node_instance_id == instance_id:
                        print(f"Found instance ID {instance_id} on node {node_name} in cluster {cluster_name}")
                        self.cordon_node(node_name, instance_id, region_name)
                except (json.JSONDecodeError, KeyError):
                    break

        except Exception as e:
            print(f"Error: {e}")

    def cordon_node(self, node_name, instance_id, region_name):
        try:
            # Cordon the node
            subprocess.run(["kubectl", "cordon", node_name])

            print(f"Node {node_name} cordon successful")

            v1 = client.CoreV1Api()

            # Get all pods running on the node
            all_node_pods = v1.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name}"
            ).items

            # Filter out DaemonSet pods
            filtered_pods = [
                pod for pod in all_node_pods if not any(owner.kind == "DaemonSet" for owner in pod.metadata.owner_references)
            ]

            # Get the StatefulSet names associated with the pods

            for pod in filtered_pods:
                namespace = pod.metadata.namespace
                pod_name = pod.metadata.name

                sts_name = self.get_statefulset_name(pod_name, namespace)

                if sts_name:
                    print(f"Pod {pod_name} in Namespace {namespace} belongs to StatefulSet {sts_name}")

                    # Get the original replica count
                    original_replicas = self.get_original_replicas(sts_name, namespace)

                    if original_replicas is not None:
                        print(f"Original replicas for StatefulSet {sts_name} in Namespace {namespace}: {original_replicas}")

                        # current replica count
                        api_instance = client.AppsV1Api()
                        statefulset = api_instance.read_namespaced_stateful_set(sts_name, namespace)
                        current_replicas = statefulset.spec.replicas

                        # multiprocess task
                        self.restart_pods_on_node(node_name, current_replicas, original_replicas, namespace)
                        #self.scale_and_restart_statefulset(sts_name, namespace, current_replicas, original_replicas)

                    else:
                        print(f"Error getting original replicas for StatefulSet {sts_name} in Namespace {namespace}")

                else:
                    print(f"Error getting StatefulSet name for pod {pod_name} in Namespace {namespace}")

        except Exception as e:
            print(f"Error cordon node {node_name} and performing operations: {e}")

    def scale_and_restart_statefulset(self, sts_name, namespace, current_replicas, original_replicas):
        new_replicas = current_replicas + 1  # Increase replica count by 1
        try:
            api_instance = client.AppsV1Api()
            statefulset = api_instance.read_namespaced_stateful_set(sts_name, namespace)
            statefulset.spec.replicas = new_replicas
            api_instance.patch_namespaced_stateful_set(sts_name, namespace, statefulset)
            print(f"Waiting for pods to initialize...")
            time.sleep(10)
            print(f"Scaled up StatefulSet {sts_name} in Namespace {namespace} to {new_replicas} replicas")

            # Rolling restart for the StatefulSet
            subprocess.run(["kubectl", "rollout", "restart", f"sts/{sts_name}", "-n", namespace])
            print(f"Rolling restart initiated for StatefulSet {sts_name} in Namespace {namespace}")
            time.sleep(10)

            self.scale_down_sts(sts_name, namespace, original_replicas)

        except Exception as e:
            print(f"Error scaling and restarting StatefulSet {sts_name} in Namespace {namespace}: {e}")

    def scale_down_sts(self, sts_name, namespace, original_replicas):
        try:
            apps_v1 = client.AppsV1Api()

            # Get the current stateful set
            statefulset = apps_v1.read_namespaced_stateful_set(sts_name, namespace)

            statefulset.spec.replicas = original_replicas
            apps_v1.patch_namespaced_stateful_set(sts_name, namespace, statefulset)

            print(f"Scaled down StatefulSet '{sts_name}' in namespace '{namespace}' to {original_replicas} replicas")
        except client.exceptions.ApiException as e:
            print(f"Error scaling down StatefulSet: {e}")

    def restart_pod(self, pod_name, namespace):
        # Restart the pod with replica count < 2
        try:
            subprocess.run(["kubectl", "delete", "pod", pod_name, "-n", namespace])
            print(f"Restarting initiated for pod '{pod_name}' in namespace '{namespace}'")
        except subprocess.CalledProcessError as e:
            print(f"Error performing restart for pod: {e}")

    def restart_pods_on_node(self, node_name, current_replicas, original_replicas, namespace):
        try:
            processes = []

            for pod in pods:
                if pod.spec.replicas > 2:
                    # Scaling and restart in parallel
                    process = multiprocessing.Process(
                        target=self.scale_and_restart_statefulset,
                        args=(pod.metadata.name, pod.metadata.namespace, current_replicas , original_replicas)
                    )
                elif pod.spec.replicas < 2:
                    process = multiprocessing.Process(
                        target=self.restart_pod,
                        args=(pod.metadata.name, pod.metadata.namespace)
                    )
                if process is not None:
                    process.start()
                    processes.append(process)

            for process in processes:
                process.join()

            print("Pods on the node restarted successfully.")
        except Exception as e:
            print(f"Error restarting pods on node {node_name}: {e}")
