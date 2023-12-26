Notes for Kubernetes Scheduler Configuration.
*********************************************

In order to run our Scheduler implementation, a functional Kubernetes cluster is needed!

*Instructions for a local deployment using Virtual Machines as worker nodes instead of real servers.

    Pre-requisites To Install Kubernetes:

    Since we are dealing with VMs, we recommend the following settings for the VMs:

    Master:

        - 2 GB RAM
        - 2 Cores of CPU

    Slave/ Node:

        - 1 GB RAM
        - 1 Core of CPU
    
After this you can start with the installation process and the creation of the Kubernetes Cluster.
When your cluster is already created and the worker nodes are connected with the master node, you can start
with the deployment of our Kubernetes Scheduler.


*Steps for redisDB deployment:

Because the redisDB is used from the latency_measurement application in order to save the network measurement result,
is needed to created first.

    1. On the master node transfer the folder 'deployments'. This folder contains all the deployment files that
       the master needs in order to apply the applications in the kubernetes cluster. Also it inculdes another files
       'redis-configuration' that contains the yaml files that are needed in order to create out DataBase in our Cluster.

    2. Apply the following files in order to create the persistent volume and persistent volume claim for data persistency:

            - redis-pv.yaml
            - redis-pvc.yaml

    3. Finally, apply the following file in order to create the redisDB in your cluster:

            - redis-master.yaml

    4. After these quick steps you will see a pod of redisDB running on a worker node.


*Steps for Latency Measurement deployment:

    1. On the node that you want your latency measurement to be deployed you need to transfer the folder 'Latency Measurement'.
       This folder contains:

            - measurement.py ---> Our latency_measurement program.
            - Dockerfile ---> Is used to build the docker image of k8s-scheduler.
            - configs
            
    2. Build the Docker image measurement.

    3. In the deployment files on your master node, apply the 

            - latency-measurement.yaml

    4. After these quick steps you will see a pod of the latency_measurement running on the specific worker node and make the required
       measurements. In addition, if you check you redisDB pod, your will observe all these measurements under 'network-latencies'.


*Steps for Kubernetes Scheduler deployment:

    1. On the node that you want your Scheduler to be deployed you need to transfer the folder 'K8s-Scheduler'.
       This folder contains:
            
            - k8s-scheduler.py ---> Our Scheduler program.
            - Dockerfile
            - configs
    
    2. At first you need to deploy the following YAML file in Configs folder:

            -custom-role.yaml ---> Define permissions on cluster scoped resources like, pods, nodes, services, etc.

    3. Build the Docker image k8s-scheduler.


    4. On the master node transfer the folder 'deployments'. This folder contains all the deployment files that
       the master needs in order to apply the applications in the kubernetes cluster.

       ** Check the name of youe k8s-scheduler images in crictl and update the name of the image in the k8s-scheduler.yaml file.

            - Apply the k8s-scheduler.yaml.
    
    5. After these quick steps you will see a pod of the k8s-scheduler running on the specific worker node.
