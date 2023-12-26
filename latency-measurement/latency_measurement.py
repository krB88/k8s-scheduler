from kubernetes import client, config
from configs import config as custom_config
from kubernetes.stream import stream
import itertools
import time
import numpy as np
import redis

class LatencyMonitor:
    def __init__(self):
        try:
            #Give the permision to Pods to have access and connect to Kubernetes Cluster.
            config.load_incluster_config()
        except FileNotFoundError as e:
                print("Warning %s\n" % e)
        self.r = redis.Redis(host='redis-master', port=6379, db=1);
        self.v1 = client.CoreV1Api()

    #Implements the periodic call of the measurement function. The MEASUREMENT_TIME is already defined in the /configs/config.py file.
    def measure_latency_with_ping_pods(self):
        rtt_matrix = self.measurement()
        print(rtt_matrix)
        timeout = custom_config.MEASUREMENT_TIME

        while True:
            if timeout > 0:
                timeout -= 1
            else:
                rtt_matrix = self.measurement()
                print(rtt_matrix)
                timeout = custom_config.MEASUREMENT_TIME
            time.sleep(1)
    
    #Call all the required functions for the creation and the deployment of the ping-pods on the related nodes and the measuring phase.
    # Finally, return the rtt_matrix which has all the network latency values for each pair of nodes in our cluster. 
    def measurement(self):
        nodes = self.get_worker_node_names()
        print("Ready nodes: {}\n\n".format(str(nodes)))
        #Create the names of the ping-pods. For example the ping-pod on the 'knode3' will be 'ping-pod-knode3'.
        ping_pod_list = ["ping-pod-{}".format(i) for i in nodes]
        pod_nodes_mapping = {ping_pod_list[i]: nodes[i] for i in range(len(ping_pod_list))}
        #Initialize the ping-pod's IP with 'None'.
        temp_pod_IPs = {ping_pod_list[i]: None for i in range(len(ping_pod_list))}
        pod_IPs = self.get_ping_pod_IPs(ping_pod_list, temp_pod_IPs)

        self.deploy_rtt_deployment(pod_IPs, pod_nodes_mapping)
        self.check_rtt_deployment(ping_pod_list)

        pod_IPs = self.get_ping_pod_IPs(ping_pod_list, pod_IPs)
        pod_rtt_matrix = self.do_measuring(pod_IPs, ping_pod_list)

        self.r.hset("network-latencies", mapping=pod_rtt_matrix)
        print("rtt-martix : ", pod_rtt_matrix, "\n\n")
        return pod_rtt_matrix
    
    #Finds and saves all the working nodes with status "Ready" in order to deploy later on them the ping-pods. We exclude the master-node!
    #Returns a list with all the available Ready Worker Nodes.
    def get_worker_node_names(self):
        ready_nodes = []
        for n in self.v1.list_node(watch=False).items:
            for status in n.status.conditions:
                if status.status == "True" and status.type == "Ready" \
                    and custom_config.MASTER_NAME not in n.metadata.name:
                    ready_nodes.append(n.metadata.name)
        return ready_nodes

    #Find the IP address of each existent ping-pod in our cluster.
    #Returns a dictionary to map the ping-pod with its IP address, dict([ping-pod-name, ping-pod-IP])
    def get_ping_pod_IPs(self, ping_pods, pod_IPs):

        ret = self.v1.list_pod_for_all_namespaces(watch=False)
        for i in ret.items:
            if str(i.metadata.name) in ping_pods:
                pod_IPs[i.metadata.name] = i.status.pod_ip
        return pod_IPs

    #Deploy on the related node the ping-pods with IP = 'None'. If after the call of the 'get_ping_pod_IPs()' the IP of a ping-pod is None
    #That means that is undeployed in our cluster.
    def deploy_rtt_deployment(self, pod_IPs, pod_node_mapping):

        for pod, pod_ip in pod_IPs.items():
            if pod_ip is None:
                template = self.create_pod_template(pod, pod_node_mapping[pod])
                body = client.V1Pod(metadata=template.metadata, spec=template.spec)
                api_response = self.v1.create_namespaced_pod(custom_config.NAMESPACE, body)
    
    #Checks if the ping-pods are running succesfully.
    def check_rtt_deployment(self, ping_pods):

        for pod in ping_pods:
            running = False
            time_out = 120
            cur_time = 0
            while cur_time < time_out:
                resp = self.v1.read_namespaced_pod(name=pod, namespace=custom_config.NAMESPACE)
                if resp.status.phase == 'Running':
                    running = True
                    break
                time.sleep(1)
                cur_time += 1
            if not running:
                raise Exception("TIMEOUT: Pod {} is not running".format(pod))

    #Create V1PodTemplateSpec object in order to deploy the ping-pod on the related worker node.
    def create_pod_template(self, pod_name, node_name):
        #Configureate Pod template container
        container = client.V1Container(
            name=pod_name,
            image=custom_config.PING_POD_IMAGE,
            command=['/sbin/init'])

        # Create and configurate a spec section
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(name=pod_name),
            spec=client.V1PodSpec(containers=[container], node_selector={"kubernetes.io/hostname": node_name}))
        return template

    #Measure the latencies of all the pairs of ping-pods that exist in the cluster.
    def do_measuring(self, pod_IPs, ping_pods):

        ping_pods_permutations = list(itertools.permutations(ping_pods, 2))
        rtt_matrix = {"{} - {}".format(i,j): np.inf for (i, j) in ping_pods_permutations}

        for i, j in ping_pods_permutations:
            if rtt_matrix["{} - {}".format(i,j)] == np.inf:
                print("\tMeasuring {} <-> {}".format(i, j))
                rtt_matrix["{} - {}".format(i,j)] = self.measure_rtt(i, pod_IPs[j])
                rtt_matrix["{} - {}".format(j,i)] = rtt_matrix["{} - {}".format(i,j)]
        return rtt_matrix

    #Measure the latency between 2 pods.
    #Returns the average round trip time between the 2 pods.
    def measure_rtt(self, pod_from, pod_to_IP):
        #we use the 'ping' command in order to take the average round trip time between the 2 pods.
        exec_command = ['/bin/sh', '-c', 'ping -c 5 {}'.format(pod_to_IP)]
        resp = stream(self.v1.connect_get_namespaced_pod_exec, pod_from, custom_config.NAMESPACE,
                        command=exec_command,
                        stderr=True, stdin=False,
                        stdout=True, tty=False)

        rtt_line = next(line for line in resp.split('\n') if 'rtt min/avg/max/mdev' in line)
        min_rtt = rtt_line.split('/')[3]
        avg_rtt = rtt_line.split('/')[4]
        max_rtt = rtt_line.split('/')[5]
        return float(avg_rtt)

def main():
    measurement = LatencyMonitor()
    measurement.measure_latency_with_ping_pods()

if __name__=="__main__":
    main()



