from cmath import log10
from kubernetes import client, config
from configs import config as custom_config
from datetime import datetime, timedelta
from kubernetes.client.rest import ApiException
import numpy as np
import math
import time
import redis
import uuid

from flask import Flask, request

class k8s_scheduler:
    
    def __init__(self):
        try:
            config.load_incluster_config()
        except FileNotFoundError as e:
            print("Warning %s\n" % e)
        self.v1 = client.CoreV1Api()
        self.api_client = client.ApiClient(configuration=None)
        self.custom_api = client.CustomObjectsApi(self.api_client)
        self.r = redis.Redis(host='redis-master', port=6379, db=1)
    
    def task_buffer_waiting_times(self, task_metrics_on_pods, task_buffer):
        #FUNCTIONALITY: Calculate the waiting time before execution of the task and append the task to the selected for assignment pod's task buffer.
        #RETURN : The Pod that is eligible for data offloading.
        #ARGS : 
        #   * task_metrics_on_pods (dict[str, dict]) : Stores execution_time and latency of the task on each pod.
        #   * task_buffer (dict[str, list]) : Stores a list with running tasks on each pod.

        #expired_tasks :  List with the expired tasks in the buffer.
        expired_tasks = []

        for pod in task_metrics_on_pods.keys():
            previous_task_completion_time = 0
            expired_completion_times = 0
            if pod in task_buffer.keys():

                for i in range(len(task_buffer[pod])):
                    #Delete expired tasks and update the completion_times of the remaining tasks
                    if task_buffer[pod][i]["start_time"] + timedelta(seconds=task_buffer[pod][i]["completion_time"]) < datetime.now():
                        expired_tasks.append(i)
                        expired_completion_times = expired_completion_times + task_buffer[pod][i]["completion_time"]
                        print("**Expired Task", task_buffer[pod][i]["id"], "on pod ", pod, "**\n")
                    else:
                        task_buffer[pod][i]["completion_time"] = task_buffer[pod][i]["completion_time"] - expired_completion_times
                #Delete the expired tasks.
                if len(expired_tasks) > 0:
                    for task in range(len(expired_tasks)):
                        task_buffer[pod].remove(task_buffer[pod][0])
                    del expired_tasks[:]       

                #Index of the new task in the task buffer of each pod
                task_buffer_index = self.task_buffer_index_search(task_buffer[pod], task_metrics_on_pods[pod]["exec_time"])

                if task_buffer_index > 0:
                    previous_task_completion_time = task_buffer[pod][task_buffer_index - 1]["completion_time"] 
                else:
                    previous_task_completion_time = 0

                #Calculate the new_task's completion_time
                #If latency > previous_task_completion_time, the completion_time of the new task is exempted from the previous_task_completion_time
                #If latency < previous_task_completion_time, the completion_time of the new task is exempted from the latency
                if task_metrics_on_pods[pod]["latency"] > previous_task_completion_time:
                    task_metrics_on_pods[pod]["completion_time"] = task_metrics_on_pods[pod]["latency"] + task_metrics_on_pods[pod]["exec_time"]
                    task_metrics_on_pods[pod]["index"] = task_buffer_index
                else:
                    task_metrics_on_pods[pod]["completion_time"] = previous_task_completion_time + task_metrics_on_pods[pod]["exec_time"]
                    task_metrics_on_pods[pod]["index"] = task_buffer_index
            else:
                task_metrics_on_pods[pod]["completion_time"] = task_metrics_on_pods[pod]["exec_time"] + task_metrics_on_pods[pod]["latency"]
                task_metrics_on_pods[pod]["index"] = 0

        #Find the pod with the minimum completion time
        pod_for_task_assignment = min(task_metrics_on_pods.keys(), key=(lambda k: task_metrics_on_pods[k]["completion_time"]))
    
        #New task building on task buffer.
        task_id = uuid.uuid1()
        print("_____________________________________________TASK", task_id, "__________________________________________________________\n\n")
        print("Task Metrics on Each Available Pod:\n")
        for key, value in task_metrics_on_pods.items():
            print(key, ":", value, "\n\n")
        
    
        if task_metrics_on_pods[pod_for_task_assignment]["index"] > 0:
            previous_task_start_time = task_buffer[pod_for_task_assignment][task_metrics_on_pods[pod_for_task_assignment]["index"]-1]["start_time"]
            previous_task_completion_time = task_buffer[pod_for_task_assignment][task_metrics_on_pods[pod_for_task_assignment]["index"]-1]["completion_time"]
            new_task_start_time =  previous_task_start_time +timedelta(seconds = previous_task_completion_time) 
        else:
            new_task_start_time = datetime.now()
    
        new_task_exec_time = task_metrics_on_pods[pod_for_task_assignment]["exec_time"]
        new_task_completion_time = task_metrics_on_pods[pod_for_task_assignment]["completion_time"]
        #Create the new task object in order to insert it in the task buffer.
        new_task = {"id": task_id, "task_buffer_arrival_time": datetime.now(), "start_time" : new_task_start_time, "exec_time" : new_task_exec_time, "completion_time" : new_task_completion_time} 
    
        if pod_for_task_assignment in task_buffer.keys(): 
            task_buffer[pod_for_task_assignment].insert(task_metrics_on_pods[pod_for_task_assignment]["index"], new_task)

            #Update the completion_time and the start_time of all the following tasks after the insertion of the new task in the buffer.
            for task in range(task_metrics_on_pods[pod_for_task_assignment]["index"]+1, len(task_buffer[pod_for_task_assignment])):
                task_buffer[pod_for_task_assignment][task]["start_time"] = task_buffer[pod_for_task_assignment][task]["start_time"] + timedelta(seconds = new_task_exec_time)
                task_buffer[pod_for_task_assignment][task]["completion_time"] = task_buffer[pod_for_task_assignment][task]["completion_time"] + new_task_exec_time
        else: 
            task_buffer[pod_for_task_assignment] = [new_task]

        return pod_for_task_assignment, task_metrics_on_pods[pod_for_task_assignment], task_buffer

    def task_buffer_index_search(self, task_buffer, task_exec_time):
        #FUNCTIONALITY : Searching of the index that the new tasks belongs in the task buffer, by using the concept of binary search.
        #RETURN : Index of the new task.
        #ARGS : 
        #   * task_buffer (List) : List of the tasks on a specific pod.
        #   * task_exec_time : The value which the function use in order to make the comparisons and finally find the index that the task belongs.

        #Set the pointers in the task_buffer for binary search purposes.
        if len(task_buffer) > 1:
            low = 1
            high = len(task_buffer) - 1
            middle = 0
        else:
            low = 0
            high = len(task_buffer) - 1
            middle = 0

        while low <= high:
            middle = (high + low) // 2
            #Ignore left sublist and set the bigger_than_middle = True.
            if task_buffer[middle]["exec_time"] < task_exec_time:
                bigger_than_middle = True
                low = middle + 1
            #Ignore right sublist and set the bigger_than_middle = False
            elif task_buffer[middle]["exec_time"] > task_exec_time:
                bigger_than_middle = False
                high = middle - 1
            # means task_exec_time is present at middle
            else:
                return middle+1

        # At the end of the loop we return the eligible index of the new task.
        if len(task_buffer) != 0:
            if(bigger_than_middle == True):
                return middle + 1
            elif(bigger_than_middle==False):
                if (middle == 0):
                    return middle + 1
                else:
                    return middle
        else:
            return 0

    def get_pod_for_task_assignment(self, input_size, end_device_name, service_selector, namespace, task_buffer):

        #FUNCTIONALITY: Based on the service_selector arg, extract the time complexity of the requested app and the pods under this kubernetes_service.
        #RETURN: The Pod that is eligible for task assignment, its completion time and the task_buffer.
        #ARGS:
        #    *input_size (number): the input size of the code in order to use it in the time complexity.
        #    *end_device_name (str): The name of the end-device that sends the request to the scheduler.
        #    *service_selector (str): Label of the kubernetes_service in order to create a relation between the kubernetes_service and the pods.
        #    *namespace (str): The namespace that the pods exist.
        #    * task_buffer (dict[str, list]) : For every pod stores a list with running tasks on it.

        placed_pods_on_nodes = dict({})

        #Find the kubernetes_service using the service_selector label
        app_service = self.v1.list_namespaced_service(namespace, field_selector = service_selector)
    
        #Find the complexity of the requested application
        app_time_complexity = app_service.items[0].metadata.annotations['complexity']
        #Extract the label-selector of the kubernetes_service. Label-selector connects the kubernetes_service with the related pods
        service_label_selector = app_service.items[0].spec.selector
        service_label_selector_key = list(service_label_selector.keys())
        service_label_selector_value = list(service_label_selector.values())
    
        #Save pods which are assigned on the kubernetes_service.
        service_assigned_pods = self.v1.list_namespaced_pod(namespace, label_selector = "{}={}".format(service_label_selector_key[0], service_label_selector_value[0]))
        for pod in service_assigned_pods.items:
            placed_pods_on_nodes = self.add_values_in_dict(placed_pods_on_nodes, pod.spec.node_name, pod.status.pod_ip, pod.metadata.name, pod.spec.containers[0].resources.limits["cpu"])
    
        #Calculate the task's execution time on each pod and the network latency between the end device and the server.
        task_metrics_on_pods = self.get_task_metrics_on_pods(input_size, app_time_complexity, placed_pods_on_nodes, end_device_name)
        pod_for_task_assignment, new_task_completion_time_index, task_buffer = self.task_buffer_waiting_times(task_metrics_on_pods, task_buffer)
    
        return pod_for_task_assignment, new_task_completion_time_index, task_buffer 

    #Create a dictionary with key the node-name and value a list of related pods placed on this node.
    def add_values_in_dict(self, placed_pods_on_nodes, node_name, pod_ip, pod_name, cpu_limit):
        if node_name not in placed_pods_on_nodes:
            placed_pods_on_nodes[node_name] = list()
        placed_pods_on_nodes[node_name].append({'pod_ip' : pod_ip, 'pod_name' : pod_name, 'pod_cpu_limit':cpu_limit})
        return placed_pods_on_nodes

    def get_task_metrics_on_pods(self, n, app_time_complexity, placed_pods_on_nodes, end_device_name):

        #FUNCTIONALITY: Calculate the execution time and network latency of the task on each pod.
        #RETURNS: Dictionary 'task_metrics_on_pods' with the execution time and the latency of each pod.
        #ARGS:
        #   *n (number): the input size in order to use it in the time complexity. The time_complexity is stored as for ex. "n*log10(n)".
        #   *app_time_complexity (str): The complexity of the code.
        #   *placed_pods_on_nodes (dict[nodes_names, dict]): Dictionary that relates the nodes_names and the related pods.
        #   *end_device_name (str): The name of the end-device that sends the request to the scheduler.

        #task_metrics_on_pods : The type is Dictionary. In the end of the execution of the scheduler we have all the metrics stored in it,
        # like [pod:{execution_time, latency, completion_time, task_buffer_index}]. In this function we fill the dictionary only with the 
        # execution_time and latency values. 
        task_metrics_on_pods = dict({})
        nodes_names = list(placed_pods_on_nodes.keys())
    
        for node in nodes_names:
            node_gflops_by_core = custom_config.CPU_DETAILS_WORKERS[node]["gflops"] / custom_config.CPU_DETAILS_WORKERS[node]["cores"]
            if node != end_device_name:
                for i in range(len(placed_pods_on_nodes[node])):
                    pod_ip = placed_pods_on_nodes[node][i]["pod_ip"]
                    pod_execution_time = eval(app_time_complexity)/(node_gflops_by_core * 1000000000)
                    task_metrics_on_pods[pod_ip] = {"exec_time" : pod_execution_time.real, "latency":float(self.r.hget("network-latencies", "ping-pod-{} - ping-pod-{}".format(end_device_name, node)).decode('utf-8'))}
            else:
                 for i in range(len(placed_pods_on_nodes[end_device_name])):
                    pod_ip = placed_pods_on_nodes[end_device_name][i]["pod_ip"]
                    pod_execution_time = eval(app_time_complexity)/(node_gflops_by_core * 1000000000)
                    task_metrics_on_pods[pod_ip] = {"exec_time" : pod_execution_time.real, "latency" : 0}

        return task_metrics_on_pods

def main():
    scheduler = k8s_scheduler()
    task_buffer = dict({})
    input_sizes = np.random.randint(6000000000,9000000000,12)
    for size in input_sizes:
        pod_for_task_assignment, new_task_completion_time_index, task_buffer = scheduler.get_pod_for_task_assignment(size, 'charlier', "metadata.name=sorting", "default", task_buffer)
        print("ASSIGN TASK TO : ", pod_for_task_assignment, "--->", new_task_completion_time_index, "\n\n")
        print("********************* Task Buffer ", pod_for_task_assignment, "*********************\n")
        for assigned_task in task_buffer[pod_for_task_assignment]:
            print(assigned_task, "\n\n")
        print("*************************************************************************\n\n")



    print("---------------------------------------------------------------- TASK BUFFERS FINAL STATE --------------------------------------------------\n\n")

    for pod in task_buffer.keys():
        print("********************* Task Buffer ", pod, "*********************\n")
        for assigned_task in task_buffer[pod]:
            print(assigned_task, "\n\n")


if __name__=="__main__":
    main()
