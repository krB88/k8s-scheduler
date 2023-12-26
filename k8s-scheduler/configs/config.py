MEASUREMENT_TIME = 60
NAMESPACE = "default"

MASTER_NAME = 'icelab' #Replace with the name of you control plane node.
PING_POD_IMAGE = 'ianneub/network-tools:latest'

CPU_DETAILS_WORKERS = ({"charlier" : {"gflops" : 13.49, "cores": 4}, "typhon" : {"gflops" : 81.29, "cores": 8}, "hyperion" : {"gflops" : 391, "cores": 24}}) #Replace with the CPU details of your worker nodes.
