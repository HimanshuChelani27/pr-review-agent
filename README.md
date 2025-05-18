# PR Review Agent

A FastAPI-based application that uses Celery for asynchronous task processing and OpenAI for automated PR reviews. This project provides an API endpoint to analyze pull requests and generate review comments using AI.

## Features

- FastAPI REST API for PR review requests
- Asynchronous task processing with Celery
- OpenAI integration for intelligent PR analysis
- Redis for task queue management
- Docker support for easy deployment

## Prerequisites

- Python 3.11+
- Redis Server
- OpenAI API Key
- Docker (optional)

## Project Structure

```
.
├── api/            # API endpoints and routes
├── core/           # Core functionality and utilities
├── tasks/          # Celery task definitions
├── clients/        # External service clients
├── app.py          # FastAPI application entry point
├── celery_app.py   # Celery configuration
├── config.py       # Application configuration
├── requirements.txt # Python dependencies
└── Dockerfile      # Docker configuration
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/HimanshuChelani27/pr-review-agent.git
cd pr-review-agent
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
Create a `.env` file in the root directory with:
```
REDIS_HOST=localhost
REDIS_PORT=6379
AZURE_OPENAI_KEY=azure_openai_key
AZURE_OPENAI_ENDPOINT=azure_openai_endpoint
AZURE_OPENAI_DEPLOYEMENT_NAME=azure_openai_deployement_name
```

## Running the Application

### Local Development

1. Start Redis server:
```bash
redis-server
```

2. Start the FastAPI application:
```bash
python app.py
```

3. Start the Celery worker:
```bash
celery -A celery_app worker --pool=solo --loglevel=info
```

### Using Docker

1. Build the Docker image:
```bash
docker build -t pr-review-agent .
```

2. Run the container:
```bash
docker run -p 8000:8000 pr-review-agent
```

## API Endpoints

### 1. Analyze a Pull Request
**POST** `/api/analyze-pr`

Analyzes a pull request and initiates a background task using Celery and OpenAI.

**Request Body**
```json
{
  "pr_url": "https://github.com/username/repo/commit/sha",
  "github_token": "your_github_token"
}
```

**Curl Example**
```bash
curl -X 'POST' \
  'http://localhost:8000/api/analyze-pr' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "pr_url": "https://github.com/username/repo/commit/sha",
  "github_token": "your_github_token"
}'
```

**Successful Response (HTTP 202)**
```json
{
  "task_id": "your-task-id",
  "status": "processing",
  "message": "PR review task created",
  "error": null,
  "result": null
}
```

### 2. Get Task Status
**GET** `/api/status/{task_id}`

Checks the current status of a PR analysis task.

**Curl Example**
```bash
curl -X 'GET' \
  'http://localhost:8000/api/status/your-task-id' \
  -H 'accept: application/json'
```

**Successful Response (HTTP 200)**
```json
{
  "task_id": "your-task-id",
  "status": "PROGRESS",
  "message": "Analyzing PR...",
  "error": null,
  "result": null
}
```

### 3. Get Task Result
**GET** `/api/results/{task_id}`

Fetches the final review results of a completed task.

**Curl Example**
```bash
curl -X 'GET' \
  'http://localhost:8000/api/results/your-task-id' \
  -H 'accept: application/json'
```

**Successful Response (HTTP 200)**
```json
{
  "task_id": "your-task-id",
  "status": "SUCCESS",
  "message": "Task completed successfully",
  "error": null,
  "result": {
    "status": "completed",
    "review": {
      "review": "# Code Review for `main.py`\n\n## Overview\n...\n"
    }
  }
}
```


## Acknowledgments

- FastAPI for the web framework
- Celery for task queue management
- OpenAI for AI capabilities
- Redis for message broker
