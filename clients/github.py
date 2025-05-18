from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Dict, Any, Optional
import logging
import requests
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('pr_review_agent')
class GitHubClient:
    """GitHub API client with retry capabilities"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.headers = {"Authorization": f"token {token}"} if token else {}
        if not token:
            logger.warning("No GitHub token provided. API rate limits may apply.")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException)
    )
    def make_request(self, url: str, headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """Make a request to GitHub API with retry logic"""
        request_headers = {**self.headers, **(headers or {})}
        response = requests.get(url, headers=request_headers)
        response.raise_for_status()
        return response
    
    def get_commit_data(self, owner: str, repo: str, commit_sha: str) -> Dict[str, Any]:
        """Get commit metadata and diff"""
        commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
        
        # Get commit metadata
        metadata_headers = {"Accept": "application/vnd.github.v3+json"}
        metadata_response = self.make_request(commit_url, metadata_headers)
        metadata = metadata_response.json()
        
        # Get commit diff
        diff_headers = {'Accept': 'application/vnd.github.v3.diff'}
        diff_response = self.make_request(commit_url, diff_headers)
        diff = diff_response.text
        
        return {"metadata": metadata, "diff": diff}
    
    def get_pr_data(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """Get PR metadata and diff"""
        pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        
        # Get PR metadata
        metadata_headers = {"Accept": "application/vnd.github.v3+json"}
        metadata_response = self.make_request(pr_url, metadata_headers)
        metadata = metadata_response.json()
        
        # Get PR diff
        diff_headers = {'Accept': 'application/vnd.github.v3.diff'}
        diff_response = self.make_request(pr_url, diff_headers)
        diff = diff_response.text
        
        return {"metadata": metadata, "diff": diff}
