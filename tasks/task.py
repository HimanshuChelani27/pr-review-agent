# tasks.py
from celery_app import celery_app
from core.langgraph_agent import pr_review_agent

@celery_app.task(bind=True)
def run_pr_review(self, pr_url, github_token=""):
    """
    Run PR review with proper error handling and task state updates
    """
    try:
        # Update task state to show it's in progress
        self.update_state(state='PROGRESS', meta={'status': 'Analyzing PR...'})
        # Run the PR review
        review_result = pr_review_agent(pr_url, github_token)
        return {"status": "completed", "review": review_result}

    except Exception as e:
        raise