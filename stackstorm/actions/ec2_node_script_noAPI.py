import subprocess
import json
import os
import time
from st2common.runners.base_action import Action
import multiprocessing

# Set environment variables

region_to_primary_cluster = {
    "ap-south-1": "prod-aps1",
    "us-east-1": "prod-use1",
    # Add if you have more regions
}

primary_to_subclusters = {
    "prod-use1": ["prod-2-use1", "prod-3-use1", "prod-4-use1"],
    # Add if you have more sub-regions under primary regions
}

class EC2Action(Action):
    def run(self, region_name, instance_id):  # provide sdm token as variable, if you are running through SDM
        if region_name in region_to_primary_cluster:
            print("Automation - STACKSTORM UPDATE")
            print("##############################")
            primary_cluster_name = region_to_primary_cluster[region_name]
            cluster_name = f"AWS-k8s-{primary_cluster_name}"
            print(cluster_name)
            subprocess.run(["/opt/stackstorm/packs/sdm", "connect", cluster_name], check=True, text=True)
            sdm_status = subprocess.run(["sdm", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if cluster_name in sdm_status.stdout:
                print("SDM connected")
                print(f"Connecting to kube context {cluster_name}")
                os.environ["KUBECONFIG"] = "/opt/stackstorm/packs/.kube/config"
                subprocess.run(["/opt/stackstorm/packs/kubectl", "config", "use-context", cluster_name], stdout=subprocess.PIPE, check=True, text=True)
                found_in_primary = self.find_node_and_cordon(instance_id, cluster_name)
                if not found_in_primary:
                    self.find_instance_id_in_subclusters(instance_id)
        else:
            print(f"Region {region_name} is not in the mapping. Unable to search for instance ID.")

    def find_instance_id_in_subclusters(self, instance_id):
        for primary_cluster, subclusters in primary_to_subclusters.items():
            for subcluster in subclusters:
                cluster_name = f"AWS-k8s-{subcluster}"
                print(f"Checking in subcluster: {cluster_name}")
                os.environ["SDM_ADMIN_TOKEN"] = os.environ.get("sdmtoken", "")
                os.environ["USE_SDM"] = "True"
                subprocess.run(["sdm", "connect", cluster_name], check=True, text=True)
                sdm_status = subprocess.run(["sdm", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if cluster_name in sdm_status.stdout:
                    print("SDM connected")
                    print(f"Connecting to kube context {cluster_name}")
                    subprocess.run(["/opt/stackstorm/packs/kubectl", "config", "use-context", cluster_name], check=True, text=True)
                    found_in_subcluster = self.find_node_and_cordon(instance_id, cluster_name)
                    if found_in_subcluster:
                        return

    def find_node_and_cordon(self, instance_id, cluster_name):
        try:
            # Using kubectl command to get node information
            cmd = f'/opt/stackstorm/packs/kubectl get nodes -o json --context={cluster_name}'
            result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE)
            node_data = json.loads(result.stdout)

            for node in node_data.get("items", []):
                node_name = node.get("metadata", {}).get("name", "")
                annotations = node.get("metadata", {}).get("annotations", {})
                node_id_annotation = annotations.get("csi.volume.kubernetes.io/nodeid", "")

                try:
                    node_instance_id = json.loads(node_id_annotation)["ebs.csi.aws.com"]
                    if node_instance_id == instance_id:
                        print(f"Found instance ID {instance_id} on node {node_name} in cluster {cluster_name}")
                        self.cordon_node(node_name)
                        return True
                except (json.JSONDecodeError, KeyError):
                    break

        except Exception as e:
            print(f"Error: {e}")

        return False

    def cordon_node(self, node_name):
        try:
            subprocess.run(["/opt/stackstorm/packs/kubectl", "cordon", node_name])
            print(f"Node {node_name} cordon successful")
            cmd = f'/opt/stackstorm/packs/kubectl get pods --all-namespaces --field-selector spec.nodeName={node_name} -o json'
            result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE)
            all_node_pods = json.loads(result.stdout.decode('utf-8'))['items']

            filtered_pods = [
                pod for pod in all_node_pods if not any(owner.get('kind') == "DaemonSet" for owner in pod.get('metadata', {}).get('ownerReferences', []))
            ]

            processes = []

            for pod in filtered_pods:
                namespace = pod.get('metadata', {}).get('namespace')
                pod_name = pod.get('metadata', {}).get('name')
                if ("artifactory" in pod_name or "xray" in pod_name) and ("rabbitmq" not in pod_name):
                    self.sts_name(namespace, pod_name)
                else:
                    p = multiprocessing.Process(target=self.restart_pod, args=(namespace, pod_name))
                    processes.append(p)
                    p.start()

            for p in processes:
                p.join()
        except Exception as e:
            print(f"Error: {e}")

    def sts_name(self, namespace, pod_name):
        try:
            cmd = f"/opt/stackstorm/packs/kubectl get pod {pod_name} -n {namespace} -o json"
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True)
            pod_info = json.loads(result.stdout)

            if "artifactory" in pod_name or "xray" in pod_name:
                owner_reference = pod_info.get("metadata", {}).get("ownerReferences", [])[0] if pod_info.get("metadata") else None

                if owner_reference and owner_reference.get("kind") == "StatefulSet":
                    statefulset_name = owner_reference.get("name")
                    print(f"sts name for namespace: {namespace} is: {statefulset_name}")
                    self.scale_and_restart(statefulset_name, namespace)

        except Exception as e:
            print(f"Error: {e}")

    def scale_and_restart(self, statefulset_name, namespace):
        try:
            statefulset_info = subprocess.run(
                ["/opt/stackstorm/packs/kubectl", "get", "sts", statefulset_name, "-n", namespace, "-o", "json"],
                check=True,
                capture_output=True,
                text=True,
            )
            statefulset_info_json = json.loads(statefulset_info.stdout)
            current_replicas = int(statefulset_info_json.get("spec", {}).get("replicas", 1))

            if current_replicas < 2:
                subprocess.run(
                    ["/opt/stackstorm/packs/kubectl", "scale", "sts", statefulset_name, "-n", namespace, f"--replicas={current_replicas + 1}"],
                    check=True,
                )
                print(f"Scaled up to {current_replicas + 1} replicas on {statefulset_name}")
                time.sleep(10)
            else:
                subprocess.run(
                    ["/opt/stackstorm/packs/kubectl", "rollout", "restart", f"sts/{statefulset_name}", "-n", namespace],
                    check=True,
                )
                print(f"Rolling restart initiated for StatefulSet '{statefulset_name}' in namespace '{namespace}'")

            time.sleep(15)

            subprocess.run(
                ["/opt/stackstorm/packs/kubectl", "scale", "sts", statefulset_name, "-n", namespace, f"--replicas={current_replicas}"],
                check=True,
            )
            print(f"Scaled down to {current_replicas} replicas on {statefulset_name}")

        except subprocess.CalledProcessError as e:
            print(f"Error performing scaling and restart for StatefulSet: {e}")

    def restart_pod(self, namespace, pod_name):
        try:
            subprocess.run(
                ["/opt/stackstorm/packs/kubectl", "delete", "pod", pod_name, "-n", namespace],
                check=True,
            )
            print(f"Restarting pod {pod_name}")

        except subprocess.CalledProcessError as e:
            print(f"Error performing restart action for pod: {pod_name} {e}")


if __name__ == "__main__":
    instance_id = str  # passes the instance_id from the st2 actions
    region_name = str  # pass the region_name from the st2 actions
    EC2Action().run(region_name=region_name, instance_id=instance_id)
