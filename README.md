PR Agent Integration with Celery
This project extends your existing Celery-based API to include a GitHub Pull Request review agent using LangGraph. The agent automatically analyzes GitHub PRs and provides detailed code reviews.
New Features

Fetch and analyze Pull Requests from GitHub
Generate detailed code reviews using LLMs
Create specific comments for code issues
Deliver comprehensive PR review summaries
Optionally post reviews directly to GitHub

Setup

Add required packages to your project:

bashpip install langchain-openai langgraph

Update your .env file with:

# Existing variables
OPENAI_API_KEY=your_openai_api_key
REDIS_HOST=localhost
REDIS_PORT=6379

# New variables
GITHUB_TOKEN=your_github_token
PR_REVIEW_MODEL=gpt-4  # Optional, defaults to gpt-4
API Usage
Request a PR Review
httpPOST /api/pr-review
Content-Type: application/json

{
  "pr_url": "https://github.com/username/repo/pull/123",
  "github_token": "your_github_token",
  "post_to_github": false
}
Check PR Review Status
httpGET /api/tasks/{task_id}/status
Get PR Review Results
httpGET /api/tasks/{task_id}/result
Implementation Details
This PR agent has been integrated into your existing Celery-based architecture:

app.py: Added new /api/pr-review endpoint
tasks.py: Implemented PR review functionality using LangGraph
config.py: Added GitHub token and PR agent configuration
celery_app.py: No changes required

The agent follows these steps in the review process:

Fetch PR Information: Basic PR details like title and description
Fetch Files: List of changed files and complete diff
Analyze Code: LLM-based code analysis
Generate Comments: Specific comments for each file
Prepare Final Review: Comprehensive review summary
Post Review (Optional): Post review back to GitHub

Running the Service
Start the API server:
bashuvicorn app:app --reload
Start Celery worker:
bashcelery -A tasks worker --loglevel=info
Example Response
json{
  "pr_url": "https://github.com/username/repo/pull/123",
  "title": "Feature: Add user authentication",
  "review": "This PR adds user authentication functionality...",
  "comments": [
    {
      "filename": "auth.py",
      "line_number": 42,
      "comment": "Consider adding input validation here."
    }
  ],
  "analysis": "Detailed code analysis...",
  "posted_to_github": false
}