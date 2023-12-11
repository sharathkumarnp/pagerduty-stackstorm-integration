import subprocess
import json
import time
import multiprocessing
from kubernetes import client, config


region_to_primary_cluster = {
    "ap-south-1": "prod-aps1",
    "us-east-1": "stg-use1",
}


def main(region_name, instance_id):
    if region_name in region_to_primary_cluster:
        print("Automation - STACKSTORM UPDATE")
        print("##############################")
        primary_cluster_name = region_to_primary_cluster[region_name]
        cluster_name = f"AWS-k8s-{primary_cluster_name}"
        print(cluster_name)
        subprocess.run(["sdm", "connect", cluster_name], check=True, text=True)
        sdm_status = subprocess.run(["sdm", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if cluster_name in sdm_status.stdout:
            print("SDM connected")
            print(f"Connecting to kube context {cluster_name}")
            subprocess.run(["kubectl", "config", "use-context", cluster_name], check=True, text=True)
            find_node_and_cordon(instance_id, cluster_name)

    else:
        print(f"Region {region_name} is not in the mapping. Unable to search for instance ID.")


def find_node_and_cordon(instance_id, cluster_name):
    try:
        config.load_kube_config()
        k8s_client = client.CoreV1Api()

        # Search for instance ID in annotations of nodes within the cluster
        nodes = k8s_client.list_node().items
        for node in nodes:
            node_name = node.metadata.name
            annotations = node.metadata.annotations or {}
            node_id_annotation = annotations.get("csi.volume.kubernetes.io/nodeid", "")

            try:
                node_instance_id = json.loads(node_id_annotation)["ebs.csi.aws.com"]
                if node_instance_id == instance_id:
                    print(f"Found instance ID {instance_id} on node {node_name} in cluster {cluster_name}")
                    cordon_node(node_name)
            except (json.JSONDecodeError, KeyError):
                break

    except Exception as e:
        print(f"Error: {e}")


def cordon_node(node_name):
    config.load_kube_config()
    kubectl_cli = client.CoreV1Api()
    try:
        patch_body = {
            "spec": {
                "unschedulable": True
            }
        }
        kubectl_cli.patch_node(node_name, patch_body)
        print(f"Node {node_name} cordon successful")
        get_pods(node_name)
    except Exception as e:
        print(f"Error: {e}")


def get_pods(node_name):
    kubectl_cli = client.CoreV1Api()
    # get all pods running on the node
    all_node_pods = kubectl_cli.list_pod_for_all_namespaces(
        field_selector=f"spec.nodeName={node_name}"
    ).items

    # Filtering DaemonSet pods
    filtered_pods = [
        pod for pod in all_node_pods if not any(owner.kind == "DaemonSet" for owner in pod.metadata.owner_references)
    ]

    #  list to store processes
    processes = []

    for pod in filtered_pods:
        namespace = pod.metadata.namespace
        pod_name = pod.metadata.name
        if ("artifactory" in pod_name or "xray" in pod_name) and ("rabbitmq" not in pod_name):
            sts_name(namespace, pod_name)
        else:
            # Start a new process for each pod restart
            p = multiprocessing.Process(target=restart_pod, args=(namespace, pod_name))
            processes.append(p)
            p.start()

    for p in processes:
        p.join()

def sts_name(namespace, pod_name):
    try:
        config.load_kube_config()
        kubectl_cli = client.CoreV1Api()

        # retrieve the pod by name
        pod = kubectl_cli.read_namespaced_pod(pod_name, namespace)

        # if the pod name contains "artifactory" or "xray"
        if "artifactory" in pod_name or "xray" in pod_name:
            owner_reference = pod.metadata.owner_references[0] if pod.metadata.owner_references else None

            if owner_reference and owner_reference.kind == "StatefulSet":
                statefulset_name = owner_reference.name
                print(f"sts name for namespace: {namespace} is: {statefulset_name}")
                scale_and_restart(statefulset_name, namespace)

    except Exception as e:
        print(f"Error: {e}")


def scale_and_restart(statefulset_name, namespace):
    try:
        config.load_kube_config()
        k8s_client = client.AppsV1Api()

        # Get the current replicas and StatefulSet details
        statefulset = k8s_client.read_namespaced_stateful_set(statefulset_name, namespace)
        current_replicas = statefulset.spec.replicas

        if current_replicas < 2:
            # Scale up replicas
            subprocess.run(
                ["kubectl", "scale", "sts", statefulset_name, "-n", namespace, f"--replicas={current_replicas + 1}"])
            print(f"Scaled up to {current_replicas + 1} on {statefulset_name}")
            time.sleep(10)
        else:
            # Rolling restart for the sts
            subprocess.run(["kubectl", "rollout", "restart", f"sts/{statefulset_name}", "-n", namespace])
            print(f"Rolling restart initiated for StatefulSet '{statefulset_name}' in namespace '{namespace}'")

        time.sleep(15)

        # Scale back to the original number of replicas
        subprocess.run(["kubectl", "scale", "sts", statefulset_name, "-n", namespace, f"--replicas={current_replicas}"])
        print(f"Scaled down to {current_replicas} on {statefulset_name}")
        print("=" * 30)

    except Exception as e:
        print(f"Error performing scaling and restart for StatefulSet: {e}")


def restart_pod(namespace, pod_name):
    # Restart the pod with replica count > 2
    try:
        config.load_kube_config()
        subprocess.run(["kubectl", "delete", "pod", pod_name, "-n", namespace, "--grace-period=0", "--force"])
        print(f"Restarting pod {pod_name}")

    except Exception as e:
        print(f"Error performing force delete for pod:{pod_name} {e}")


if __name__ == "__main__":
    instance_id = "i-xxx"  # Replace with the instance ID you want to search
    region_name = "xx-xxx-x"  # Replace with your AWS region name
    main(region_name, instance_id)
