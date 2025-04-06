import boto3
import os
import time
import json
import requests
from urllib.parse import unquote_plus

# Initialize S3 client
s3_client = boto3.client('s3')

# Configuration from environment variables
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_URL = os.environ.get("RUNPOD_ENDPOINT_URL")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")  # If empty, use same bucket as input
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "summaries/")

# Constants
MAX_TOKENS = 16000  # Approximate for 4000 words (4 tokens per word)
POLL_INTERVAL = 5  # Seconds between status checks
MAX_POLLING_ATTEMPTS = 60  # With 5-second intervals = ~5 minutes of polling

def lambda_handler(event, context):
    """
    AWS Lambda handler function triggered by S3 object creation events.
    Processes transcription files by sending them to RunPod for AI summarization.
    """
    try:
        # 1. Parse the S3 event notification
        print("Processing S3 event:", json.dumps(event))
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = unquote_plus(event['Records'][0]['s3']['object']['key'])

        # Use the same bucket for output if not specified
        output_bucket = OUTPUT_BUCKET if OUTPUT_BUCKET else bucket

        print(f"Processing file s3://{bucket}/{key}")

        # 2. Retrieve the transcription file content
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            text_data = response['Body'].read().decode('utf-8')
            print(f"Successfully retrieved file, size: {len(text_data)} characters")
        except Exception as e:
            print(f"Error retrieving file from S3: {str(e)}")
            raise

        # 3. Send the transcription to RunPod for summarization
        run_response = initiate_runpod_job(text_data)

        # 4. Poll for job completion
        summary = poll_runpod_job(run_response["id"])

        # 5. Store the summary in S3
        output_key = f"{OUTPUT_PREFIX}{os.path.basename(key).replace('.txt', '_summary.txt')}"
        s3_client.put_object(
            Bucket=output_bucket,
            Key=output_key,
            Body=summary.encode('utf-8'),
            ContentType='text/plain'
        )

        print(f"Summary successfully stored at s3://{output_bucket}/{output_key}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Summarization completed successfully',
                'summary_location': f"s3://{output_bucket}/{output_key}"
            })
        }

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def initiate_runpod_job(text_data):
    """
    Initiates a summarization job on RunPod.

    Args:
        text_data: The transcription text to summarize

    Returns:
        The RunPod API response containing the job ID
    """
    if not RUNPOD_API_KEY or not RUNPOD_ENDPOINT_URL:
        raise ValueError("RunPod API key or endpoint URL not configured")

    headers = {
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
        "Content-Type": "application/json"
    }

    # Prepare the payload for the Yarn LLaMA model
    payload = {
        "input": {
            "prompt": f"Please provide a comprehensive summary of the following transcription in approximately 4000 words. Focus on capturing the main points, key discussions, and important conclusions:\n\n{text_data}",
            "max_new_tokens": MAX_TOKENS,
            "temperature": 0.7,
            "top_p": 0.9
        }
    }

    try:
        print("Sending request to RunPod API")
        response = requests.post(
            f"{RUNPOD_ENDPOINT_URL}/run",
            headers=headers,
            json=payload,
            timeout=30  # Timeout for initial request
        )
        response.raise_for_status()
        result = response.json()

        if "id" not in result:
            raise ValueError(f"RunPod API did not return a job ID: {result}")

        print(f"RunPod job initiated with ID: {result['id']}")
        return result

    except requests.exceptions.RequestException as e:
        print(f"Error calling RunPod API: {str(e)}")
        if hasattr(e, 'response') and e.response:
            print(f"Response content: {e.response.content}")
        raise

def poll_runpod_job(job_id):
    """
    Polls the RunPod API for job completion.

    Args:
        job_id: The RunPod job ID to check

    Returns:
        The generated summary text

    Raises:
        TimeoutError: If polling exceeds MAX_POLLING_ATTEMPTS
        ValueError: If the job fails or returns invalid data
    """
    headers = {
        "Authorization": f"Bearer {RUNPOD_API_KEY}"
    }

    endpoint = f"{RUNPOD_ENDPOINT_URL}/status/{job_id}"

    print(f"Polling RunPod job status at: {endpoint}")

    for attempt in range(MAX_POLLING_ATTEMPTS):
        try:
            response = requests.get(
                endpoint,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            status_data = response.json()

            print(f"Poll attempt {attempt+1}/{MAX_POLLING_ATTEMPTS}, status: {status_data.get('status')}")

            if status_data.get("status") == "COMPLETED":
                # Extract the summary text from the response
                # Note: The exact structure may vary based on the RunPod endpoint configuration
                if "output" in status_data:
                    if isinstance(status_data["output"], str):
                        return status_data["output"]
                    elif isinstance(status_data["output"], dict) and "text" in status_data["output"]:
                        return status_data["output"]["text"]
                    elif isinstance(status_data["output"], list) and len(status_data["output"]) > 0:
                        # If output is a list of generations, take the first one
                        return status_data["output"][0].get("text", json.dumps(status_data["output"]))
                    else:
                        # Fallback: return the entire output as JSON
                        return json.dumps(status_data["output"])
                else:
                    raise ValueError(f"No output found in completed job: {status_data}")

            elif status_data.get("status") in ["FAILED", "CANCELLED"]:
                error_msg = f"RunPod job failed with status: {status_data.get('status')}"
                if "error" in status_data:
                    error_msg += f", error: {status_data['error']}"
                raise ValueError(error_msg)

            # Job still in progress, wait before next poll
            time.sleep(POLL_INTERVAL)

        except requests.exceptions.RequestException as e:
            print(f"Error polling RunPod API (attempt {attempt+1}): {str(e)}")
            # Continue polling despite temporary errors
            time.sleep(POLL_INTERVAL)

    # If we get here, we've exceeded MAX_POLLING_ATTEMPTS
    raise TimeoutError(f"Timed out waiting for RunPod job {job_id} after {MAX_POLLING_ATTEMPTS} polling attempts")
