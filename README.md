# Shadow Analysis

This project provides a comprehensive solution for calculating and analyzing shadows on a Digital Surface Model (DSM) based on the sun's azimuth and elevation. The application is built using Flask and integrates with MongoDB for data storage. It also leverages AWS services for deployment and Docker for containerization.

### Introduction
The main server file, `analysis.py`, orchestrates the entire process. The application calculates the shadow matrix based on the current timestamp to determine the sun's position and saves this data to MongoDB. Additionally, it generates visual representations in the form of heatmaps and surface plots to provide a graphical analysis of the shadows.

### Running the Analysis Server Locally with Docker

##### Prerequisites
* Ensure you have Docker installed on your machine.
* Ensure your MongoDB instance is accessible from the Docker container. If you're running MongoDB locally, you might need to use host.docker.internal as the hostname instead of localhost in your connection string.

```sh
git clone https://github.com/IsurangaPerera/shadow-analaysis.git
cd shadow-analysis
pip3 install -r requirements.txt
python3 deploy.py --local 
```

##### Parameters
The `deploy.py` script accepts the following parameters. If you need to use values other than the default ones for these parameters, ensure you specify them when invoking the script:

| Parameter | Default Value | Description
| ------ | ------ | ------ |
| `--port` | 80 | port that server runs on |
| `--mongodb-host` | localhost | mongodb url |
| `--mongodb-port` | 27017 | mongodb port |

### AWS Setup and Deployment
##### Prerequisites
Before proceeding with the AWS setup and deployment, ensure you have the following prerequisites in place:

1. AWS CLI Configuration: Before running the deploy.py script, you need to set up the AWS Command Line Interface (CLI). This can be done using the following command. This command will prompt you to enter your AWS access key, secret key, region, and output format. Ensure you have the necessary AWS credentials at hand.
 ```sh
 aws configure
 ```
2. AWS Key Pair: It's essential to create an AWS key pair that will be used with the `deploy.py` script. This key pair will allow you to securely connect to instances that you launch. To create a key pair:
    * Navigate to the EC2 dashboard in the AWS Management Console.
    * In the navigation pane, under "Network & Security," choose "Key Pairs."
    * Choose "Create key pair," provide a name for the key pair, and choose "Create."
    * Your private key file will automatically download; keep this file secure.
3. Complete configuration properties in `config.json` file.

To use the `deploy.py` script, navigate to your project directory and run:
```sh
python3 deploy.py
```

##### Parameters for AWS Setup
The `deploy.py` script accepts the following properties through `config.json` file. If you need to use values other than the default ones for these parameters, ensure you specify them when invoking the script:

| Property             | Description                                                                                       |
|----------------------|---------------------------------------------------------------------------------------------------|
| `dockerhub_username` | The username for Docker Hub, used for authentication during Docker image push operations.         |
| `dockerhub_password` | The password associated with the Docker Hub username.                                             |
| `dockerhub_repo`     | The name of the Docker Hub repository where the Docker image will be pushed.                      |
| `aws_key_name`       | The name of the AWS key pair used for EC2 instance authentication.                                |
| `aws_key_path`       | The local path to the AWS key pair file (usually a `.pem` file).                                  |
| `mongo_host`         | The hostname or URL of the MongoDB server or cluster.                                             |
| `mongo_password`     | The password used for authenticating to the MongoDB server or cluster.                            |
| `mongo_username`     | The username used for authenticating to the MongoDB server or cluster.                            |

### Making a Request and Understanding the Response
##### Making a Request
To retrieve the desired data, make a request to the appropriate endpoint of the deployed service. Depending on your deployment, this might be a local endpoint or a remote one provided by AWS or another cloud provider.
```sh
curl -X GET <YOUR_ENDPOINT_URL>
```
##### Response Format
The response will be a JSON object containing the following fields:
* timestamp: The timestamp indicating when the data was generated or retrieved.
* heatmap: An image representing the heatmap, encoded as a Base64 string. You can decode this string to view or save the image.
* surface-plot: An image representing the surface plot, also encoded as a Base64 string. Similarly, you can decode this string to view or save the image.

##### Sample Response
To view the images, you'll need to decode the Base64 strings. Many programming languages offer built-in methods for this, and there are also online tools available for decoding Base64.
```json
{
    "timestamp": "2023-10-16T12:34:56Z",
    "heatmap": "BASE64_ENCODED_STRING_FOR_HEATMAP_IMAGE",
    "surface-plot": "BASE64_ENCODED_STRING_FOR_SURFACE_PLOT_IMAGE"
}
```


##### `deploy.py` Implementation Overview
The `deploy.py` script automates the deployment process on AWS. Here's a brief description of the tasks carried out by the script:

1. ***Infrastructure Setup:*** The script initializes the required AWS infrastructure, including setting up Virtual Private Cloud (VPC), subnets, and security groups.
2. ***EC2 Instance Launch:*** It provisions and launches an EC2 instance using the specified AWS key pair, ensuring secure access to the instance.
3. ***Application Deployment:*** The script deploys the application on the EC2 instance, setting up necessary dependencies and starting the application services.
4. ***API Gateway Setup:*** The script configures the AWS API Gateway, which acts as a front door for your application to access data, business logic, or functionality from your backend services. This includes setting up routes, endpoints, and necessary integrations with your application.
5. ***Database Configuration:*** If your application requires a database, the script can also handle the setup and configuration of databases like RDS on AWS.
6. ***Logging and Monitoring:*** The script sets up necessary logging and monitoring tools, ensuring you have visibility into your application's performance and any potential issues.
7. ***Clean Up:*** Post-deployment, the script provides options to clean up resources, ensuring you don't incur unnecessary costs.

### Repository Contents
1. ***`config.json`*** - Contains configuration details such as Docker Hub credentials, AWS key details, and MongoDB connection information.
2. ***`analysis.py`*** - Orchestrates the shadow calculation process. Connects to MongoDB and saves shadow matrices. Generates heatmaps and surface plots for shadow visualization. Sets up the Flask server to provide an API endpoint for shadow calculation.
3. ***`deploy.py`*** - Contains the logic for deploying the Docker image to Docker Hub. Sets up AWS EC2 instances and security groups. Configures and deploys the API Gateway on AWS.
4. ***`Dockerfile`*** - Provides instructions for building the Docker image. Sets up the necessary environment variables and installs required dependencies.
5. ***`requirements.txt`*** - Lists all the Python libraries and dependencies required for the project.
6. ***`shadowingfunction_wallheight_13.py`*** - Contains the core logic for calculating shadows on a DSM. Uses mathematical calculations based on sun's azimuth and elevation to determine shadow matrices.
