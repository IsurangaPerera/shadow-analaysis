import argparse
import json
import logging
import subprocess

import boto3
import paramiko

# AWS Configuration
REGION = 'us-east-2'
EC2_INSTANCE_NAME = 'shadow-analysis-ec2'
API_GATEWAY_NAME = 'shadow-analysis-api-gateway'
SECURITY_GROUP_NAME = 'shadow-analysis-security-group'
DOCKER_IMAGE_NAME = 'shadow-analysis'
DOCKER_IMAGE_TAG = 'latest'
RESOURCE_PATH = 'shadow-analysis'
HTTP_METHOD = 'GET'

# Initialize boto3 clients
ec2 = boto3.client('ec2', region_name=REGION)
apigateway = boto3.client('apigateway', region_name=REGION)


def check_or_create_security_group():
    """
    Check if the security group exists. If not, create one and open ports for traffic.
    """
    security_groups = ec2.describe_security_groups()['SecurityGroups']
    group_ids = [sg['GroupId'] for sg in security_groups if sg['GroupName'] == SECURITY_GROUP_NAME]

    if not group_ids:
        logging.info("Creating security group...")
        response = ec2.create_security_group(GroupName=SECURITY_GROUP_NAME,
                                             Description='Security group for EC2 instance')
        group_id = response['GroupId']

        # Define rules for traffic
        rules = [
            {'type': 'HTTP', 'from_port': 80, 'to_port': 80, 'cidr_ipv4': '0.0.0.0/0'},
            {'type': 'SSH', 'from_port': 22, 'to_port': 22, 'cidr_ipv4': '0.0.0.0/0'},
            {'type': 'HTTPS', 'from_port': 443, 'to_port': 443, 'cidr_ipv4': '0.0.0.0/0'}
        ]

        # Open ports based on the defined rules
        for rule in rules:
            ec2.authorize_security_group_ingress(GroupId=group_id, IpProtocol='tcp',
                                                 FromPort=rule['from_port'], ToPort=rule['to_port'],
                                                 CidrIp=rule['cidr_ipv4'])
            logging.info(f"Opened {rule['type']} traffic on port {rule['from_port']}.")
            # Allow all outbound traffic
        ec2.authorize_security_group_egress(
            GroupId=group_id,
            IpPermissions=[
                {
                    'IpProtocol': '-1',
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                    'Ipv6Ranges': [{'CidrIpv6': '::/0'}]
                }
            ]
        )
        logging.info("Allowed all outbound traffic.")
    else:
        group_id = group_ids[0]
        logging.info("Security group already exists.")

    return group_id


def ssh_and_deploy_docker(key_path, instance_ip, docker_image):
    key = paramiko.RSAKey(filename=key_path)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Connect to the EC2 instance
    client.connect(instance_ip, username='ec2-user', pkey=key)

    # Commands to pull the latest Docker image and run it
    commands = [
        f"docker pull {docker_image}",
        "docker stop $(docker ps -q)",  # Stop the currently running container
        f"docker run -d -p 80:7001 {docker_image}"
    ]

    for command in commands:
        stdin, stdout, stderr = client.exec_command(command)
        print(stdout.read().decode(), stderr.read().decode())

    client.close()


def wait_for_ec2_running(instance_id):
    """
    Wait until the specified EC2 instance is in a running state.
    """
    logging.info(f"Waiting for EC2 instance {instance_id} to be in a running state...")
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])
    logging.info(f"EC2 instance {instance_id} is now running.")


def check_or_create_ec2_instance(key_name, key_path, repo, security_group_id):
    """
    Check if the EC2 instance exists. If not, create one. If it does, redeploy the container.
    """
    response = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': [EC2_INSTANCE_NAME]}])
    instance_states = [instance['State']['Name'] for reservation in response['Reservations'] for instance in
                       reservation['Instances']]
    docker_image = f"{repo}/{DOCKER_IMAGE_NAME}:{DOCKER_IMAGE_TAG}"

    user_data_script = f"""#!/bin/bash
    yum update -y
    yum install -y docker
    service docker start
    usermod -a -G docker ec2-user
    docker pull {docker_image}
    docker run -d -p 80:7001 {docker_image}
    """

    if not any(state in ['running', 'pending'] for state in instance_states):
        logging.info("Creating EC2 instance...")
        response = ec2.run_instances(
            ImageId='ami-080c09858e04800a1',
            InstanceType='t2.micro',
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[security_group_id],
            UserData=user_data_script,
            KeyName=key_name,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'Name', 'Value': EC2_INSTANCE_NAME}]
                }
            ]
        )
        instance_id = response['Instances'][0]['InstanceId']
        wait_for_ec2_running(instance_id)
    else:
        logging.info("EC2 instance already exists. Redeploying the container...")
        # Filter out instances that are in the 'running' state
        running_instances = [instance for reservation in response['Reservations'] for instance in
                             reservation['Instances'] if instance['State']['Name'] == 'running']

        if running_instances:
            instance_ip = running_instances[0]['PublicIpAddress']
            ssh_and_deploy_docker(key_path, instance_ip, docker_image)
        else:
            logging.error("No running instances found.")


def publish_docker_image(dockerhub_username, dockerhub_password, repo, mongo_host, mongo_username, mongo_password):
    """
    Deploy Docker image to Docker Hub.
    """
    # Step 1: Build the Docker image
    logging.info("Building Docker image...")
    subprocess.run(
        f"docker build --no-cache --platform linux/amd64 "
        f"--build-arg DB_HOST={mongo_host} "
        f"--build-arg DB_USERNAME={mongo_username} "
        f"--build-arg DB_PASSWORD={mongo_password} "
        f"--build-arg USE_SRV={True} "
        f"-t {DOCKER_IMAGE_NAME}:{DOCKER_IMAGE_TAG} .",
        shell=True,
        check=True)

    # Step 2: Authenticate Docker to Docker Hub
    subprocess.run(f"docker login -u {dockerhub_username} -p {dockerhub_password}", shell=True, check=True)

    # Step 3: Tag Docker image with Docker Hub repository name
    docker_image_dockerhub_tag = f"{repo}/{DOCKER_IMAGE_NAME}:{DOCKER_IMAGE_TAG}"
    subprocess.run(f"docker tag {DOCKER_IMAGE_NAME}:{DOCKER_IMAGE_TAG} {docker_image_dockerhub_tag}", shell=True,
                   check=True)

    # Step 4: Push the Docker image to Docker Hub
    subprocess.run(f"docker push {docker_image_dockerhub_tag}", shell=True, check=True)
    logging.info(f"Docker image pushed to: {docker_image_dockerhub_tag}")


def start_service(mongo_host, mongo_port, port, use_srv):
    """
    Run Docker container locally.
    """
    try:
        # Step 1: Build the Docker image
        logging.info("Building Docker image...")
        subprocess.run(
            f"docker build --no-cache --platform linux/amd64 "
            f"--build-arg DB_HOST={mongo_host} "
            f"--build-arg DB_PORT={mongo_port} "
            f"--build-arg USE_SRV={use_srv} "
            f"-t {DOCKER_IMAGE_NAME}:{DOCKER_IMAGE_TAG} .",
            shell=True,
            check=True)

        # Step 2: Run the Docker image
        logging.info("Running Docker container...")
        subprocess.run(f"docker run -p {port}:7001 {DOCKER_IMAGE_NAME}:{DOCKER_IMAGE_TAG}", shell=True, check=True)

        logging.info(f"Docker service can be accessed through http://localhost:{port}/calculate-shadow")

    except subprocess.CalledProcessError:
        logging.error("Error occurred while building or running the Docker container.")


def create_api_gateway():
    response = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': [EC2_INSTANCE_NAME]}])
    # Filter out instances that are in the 'running' state
    running_instances = [instance for reservation in response['Reservations'] for instance in
                         reservation['Instances'] if instance['State']['Name'] == 'running']
    instance_ip = running_instances[0]['PublicIpAddress']
    ec2_endpoint = f"http://{instance_ip}:80/calculate-shadow"

    # Create the API
    logging.info("Creating API Gateway...")
    response = apigateway.create_rest_api(
        name=API_GATEWAY_NAME,
        description='API Gateway for shadow analysis app',
        endpointConfiguration={
            'types': ['REGIONAL']
        }
    )
    api_id = response['id']

    # Get the root resource for the API
    resources = apigateway.get_resources(restApiId=api_id)['items']
    root_id = None
    for resource in resources:
        if resource['path'] == '/':
            root_id = resource['id']
            break

    # Create a new resource
    logging.info("Creating resource...")
    resource_response = apigateway.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart=RESOURCE_PATH
    )
    resource_id = resource_response['id']
    # Create an HTTP method for the resource
    logging.info("Creating HTTP method...")
    apigateway.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod=HTTP_METHOD,
        authorizationType='NONE'
    )

    # Set up the method response to specify the application/json MIME type
    apigateway.put_method_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod=HTTP_METHOD,
        statusCode='200',
        responseModels={
            'application/json': 'Empty'
        }
    )

    # Set up the integration request to connect to the EC2
    logging.info("Setting up integration request...")
    apigateway.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod=HTTP_METHOD,
        type='HTTP',
        integrationHttpMethod=HTTP_METHOD,
        uri=ec2_endpoint
    )

    # Set up the integration response to specify the application/json MIME type
    apigateway.put_integration_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod=HTTP_METHOD,
        statusCode='200',
        responseTemplates={
            'application/json': ''
        }
    )

    # Deploy the API
    logging.info("Deploying API...")
    apigateway.create_deployment(
        restApiId=api_id,
        stageName='prod',
        stageDescription='Production stage',
        description='Deploying the API'
    )

    # Create a usage plan
    logging.info("Creating Usage Plan...")
    usage_plan = apigateway.create_usage_plan(
        name='RateLimitedPlan',
        description='Usage plan with rate limiting',
        apiStages=[
            {
                'apiId': api_id,
                'stage': 'prod'
            }
        ],
        throttle={
            'burstLimit': 10,  # Maximum number of requests per second
            'rateLimit': 1000  # Maximum number of requests per day
        }
    )

    # Create an API key
    logging.info("Creating API Key...")
    api_key = apigateway.create_api_key(
        name='RateLimitedAPIKey',
        description='API Key with rate limiting',
        enabled=True
    )

    # Associate the API key with the usage plan
    logging.info("Associating API Key with Usage Plan...")
    apigateway.create_usage_plan_key(
        usagePlanId=usage_plan['id'],
        keyId=api_key['id'],
        keyType='API_KEY'
    )

    logging.info(f"API Gateway setup complete. Invoke URL: https://{api_id}.execute-api.{REGION}.amazonaws.com/prod")


def delete_resources():
    """
    Delete specified EC2 instance and API Gateway.

    Parameters:
    - ec2_instance_name: Name tag of the EC2 instance to be deleted.
    - api_gateway_name: Name of the API Gateway to be deleted.
    """

    # Initialize boto3 clients for EC2 and API Gateway
    ec2_client = boto3.client('ec2')
    apigateway_client = boto3.client('apigateway')

    # Find and terminate EC2 instance by name
    try:
        response = ec2_client.describe_instances(
            Filters=[
                {
                    'Name': 'tag:Name',
                    'Values': [EC2_INSTANCE_NAME]
                }
            ]
        )
        if response['Reservations']:
            instance_id = response['Reservations'][0]['Instances'][0]['InstanceId']
            ec2_client.terminate_instances(InstanceIds=[instance_id])
            print(f"EC2 instance with name {EC2_INSTANCE_NAME} (ID: {instance_id}) is being terminated.")
        else:
            print(f"No EC2 instance found with name {EC2_INSTANCE_NAME}.")
    except Exception as e:
        print(f"Error terminating EC2 instance with name {EC2_INSTANCE_NAME}: {e}")

    # Find and delete API Gateway by name
    try:
        response = apigateway_client.get_rest_apis()
        api_id = next((item['id'] for item in response['items'] if item["name"] == API_GATEWAY_NAME), None)
        if api_id:
            apigateway_client.delete_rest_api(restApiId=api_id)
            print(f"API Gateway with name {API_GATEWAY_NAME} (ID: {api_id}) has been deleted.")
        else:
            print(f"No API Gateway found with name {API_GATEWAY_NAME}.")
    except Exception as e:
        print(f"Error deleting API Gateway with name {API_GATEWAY_NAME}: {e}")


def main():
    logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="Run the shadow analysis server.")
    parser.add_argument('--mongo-host', type=str, default="localhost",
                        help="Host for MongoDB. Default is localhost")
    parser.add_argument('--mongo-port', type=int, default=27017,
                        help="Port for MongoDB. Default is 27017")
    parser.add_argument('--port', type=str, default="7001",
                        help="Port that service runs on.")
    parser.add_argument('--local', action='store_true',
                        help="Flag to determine if the script should run in a local environment. Default is False.")
    parser.add_argument('--purge', action='store_true',
                        help="Flag to delete and clean EC2 instance and API Gateway.")

    args = parser.parse_args()

    if args.purge:
        delete_resources()
        exit(0)

    if args.local:
        db_host = args.mongo_host
        db_port = args.mongo_port
        port = args.port
        start_service(db_host, db_port, port, False)
    else:
        with open('./config.json', 'r') as file:
            configs = json.load(file)

        security_group_id = check_or_create_security_group()
        publish_docker_image(configs['dockerhub_username'], configs['dockerhub_password'], configs['dockerhub_repo'],
                             configs['mongo_host'], configs['mongo_username'], configs['mongo_password'])
        check_or_create_ec2_instance(configs['aws_key_name'], configs['aws_key_path'], configs['dockerhub_repo'],
                                     security_group_id)
        # create_api_gateway()
        logging.info("Setup complete.")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
