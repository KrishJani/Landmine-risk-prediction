"""
AWS EC2 Helper Module
Provides functions to trigger EC2 worker instances for model training jobs.
"""
import os
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

# Initialize boto3 clients
ec2_client = None
try:
    ec2_client = boto3.client('ec2', region_name=os.getenv('AWS_REGION', 'us-east-1'))
except Exception as e:
    logger.warning(f"Could not initialize EC2 client: {e}")


def trigger_worker_instance(launch_template_name=None, max_price='0.50'):
    """
    Launch an EC2 Spot instance for model training.
    
    Args:
        launch_template_name: Name of the EC2 launch template (default: from env)
        max_price: Maximum price per hour for Spot instance (default: $0.50)
    
    Returns:
        dict: Instance information including instance_id, or None if failed
    """
    if not ec2_client:
        logger.error("EC2 client not available")
        return None
    
    # Get launch template name from environment or parameter
    template_name = launch_template_name or os.getenv('EC2_LAUNCH_TEMPLATE_NAME', 'reland-worker-template')
    
    try:
        # Get launch template ID
        response = ec2_client.describe_launch_templates(
            LaunchTemplateNames=[template_name]
        )
        
        if not response['LaunchTemplates']:
            logger.error(f"Launch template '{template_name}' not found")
            return None
        
        launch_template_id = response['LaunchTemplates'][0]['LaunchTemplateId']
        
        # Launch Spot instance
        response = ec2_client.run_instances(
            LaunchTemplate={
                'LaunchTemplateId': launch_template_id
            },
            InstanceMarketOptions={
                'MarketType': 'spot',
                'SpotOptions': {
                    'SpotInstanceType': 'one-time',
                    'InstanceInterruptionBehavior': 'terminate',
                    'MaxPrice': max_price
                }
            },
            MinCount=1,
            MaxCount=1
        )
        
        instance_id = response['Instances'][0]['InstanceId']
        instance_state = response['Instances'][0]['State']['Name']
        
        logger.info(f"Successfully launched EC2 worker instance: {instance_id} (state: {instance_state})")
        
        return {
            'instance_id': instance_id,
            'state': instance_state,
            'launch_template': template_name
        }
        
    except ClientError as e:
        logger.error(f"Failed to launch EC2 instance: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error launching EC2 instance: {e}")
        return None


def check_worker_instances():
    """
    Check for running EC2 worker instances.
    
    Returns:
        list: List of running worker instances
    """
    if not ec2_client:
        return []
    
    try:
        # Get project name from environment
        project_name = os.getenv('PROJECT_NAME', 'reland')
        
        # Describe instances with project tag
        response = ec2_client.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]},
                {'Name': 'tag:Name', 'Values': [f'{project_name}-worker*']},
                {'Name': 'instance-state-name', 'Values': ['running', 'pending']}
            ]
        )
        
        instances = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instances.append({
                    'instance_id': instance['InstanceId'],
                    'state': instance['State']['Name'],
                    'instance_type': instance['InstanceType'],
                    'launch_time': instance['LaunchTime'].isoformat()
                })
        
        return instances
        
    except Exception as e:
        logger.error(f"Error checking worker instances: {e}")
        return []


def terminate_worker_instance(instance_id):
    """
    Terminate an EC2 worker instance.
    
    Args:
        instance_id: ID of the instance to terminate
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not ec2_client:
        return False
    
    try:
        ec2_client.terminate_instances(InstanceIds=[instance_id])
        logger.info(f"Terminated EC2 worker instance: {instance_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to terminate EC2 instance {instance_id}: {e}")
        return False

