import logging
import re
import requests
import traceback
import json
from typing import TypedDict, List, Dict, Any, Optional
from functools import lru_cache
import concurrent.futures
from langgraph.graph import StateGraph, END
from clients.ai import AIClient
from clients.github import GitHubClient
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('pr_review_agent')

class ReviewState(TypedDict):
    """Type definition for the agent's state"""
    url: str
    owner: str
    repo: str
    is_commit: bool
    commit_sha: Optional[str]
    pr_number: Optional[int]
    diff: Optional[str]
    metadata: Optional[Dict[str, Any]]
    file_changes: Optional[List[Dict[str, Any]]]
    issues: List[Dict[str, Any]]
    recommendations: List[str]
    review: Optional[str]
    error: Optional[str]
    review_template: Optional[str]
    options: Optional[Dict[str, Any]]

def parse_url(state: ReviewState) -> ReviewState:
    """Parse GitHub URL to extract repo, PR or commit information"""
    logger.info("Extracting repository information from URL")
    url = state.get('url')
    
    # Check if it's a PR URL
    pr_match = re.match(r"https://github.com/(.*?)/(.*?)/pull/(\d+)", url)
    # Check if it's a commit URL
    commit_match = re.match(r"https://github.com/(.*?)/(.*?)/commit/(.*)", url)

    if pr_match:
        owner, repo, pr_number = pr_match.groups()
        logger.info(f"PR identified: Owner={owner}, Repo={repo}, PR#{pr_number}")
        return {
            **state,
            "owner": owner,
            "repo": repo,
            "pr_number": int(pr_number),
            "is_commit": False
        }
    elif commit_match:
        owner, repo, commit_sha = commit_match.groups()
        logger.info(f"Commit identified: Owner={owner}, Repo={repo}, SHA={commit_sha}")
        return {
            **state,
            "owner": owner,
            "repo": repo,
            "commit_sha": commit_sha,
            "is_commit": True
        }
    else:
        logger.error(f"Invalid GitHub URL: {url}")
        return {
            **state,
            "error": f"Invalid GitHub URL. Must be a PR or commit URL"
        }

def fetch_content(state: ReviewState) -> ReviewState:
    """Fetch PR or commit content from GitHub API"""
    if state.get("error"):
        return state
            
    owner = state.get("owner")
    repo = state.get("repo")
    is_commit = state.get("is_commit")
    github_token = state.get("options", {}).get("github_token")
    
    github_client = GitHubClient(github_token)
    
    try:
        if is_commit:
            # Handle commit URL
            commit_sha = state.get("commit_sha")
            logger.info(f"Fetching commit data for {commit_sha}")
            
            data = github_client.get_commit_data(owner, repo, commit_sha)
            metadata = data["metadata"]
            diff = data["diff"]
        else:
            # Handle PR URL
            pr_number = state.get("pr_number")
            logger.info(f"Fetching PR data for PR #{pr_number}")
            
            data = github_client.get_pr_data(owner, repo, pr_number)
            metadata = data["metadata"]
            diff = data["diff"]
        
        if len(diff) == 0:
            logger.warning("Empty diff received")
            return {**state, "error": "Diff is empty. Nothing to review.", "metadata": metadata}
        
        logger.info(f"Successfully fetched {'commit' if is_commit else 'PR'} data. Diff size: {len(diff)} characters")
        return {**state, "diff": diff, "metadata": metadata}
        
    except requests.exceptions.RequestException as e:
        error_message = f"Failed to fetch {'commit' if is_commit else 'PR'} data: {str(e)}"
        logger.error(error_message)
        return {**state, "error": error_message}

def analyze_changes(state: ReviewState) -> ReviewState:
    """Analyze the changes to identify file patterns and potential issues"""
    if state.get("error") or not state.get("diff"):
        return state
        
    logger.info("Analyzing code changes")
    diff = state.get("diff")
    
    # Get AI client from options or create a new one
    ai_client = state.get("options", {}).get("ai_client") or AIClient(
        api_key=settings.AZURE_OPENAI_KEY,
        endpoint=settings.AZURE_OPENAI_ENDPOINT,
        deployment=settings.AZURE_OPENAI_DEPLOYEMENT_NAME
    )
    
    try:
        # Analysis prompt for the model
        system_prompt = (
            "You are a code analysis expert. Analyze the given diff to extract key information: "
            "1. Identify all changed files and their types "
            "2. For each file, identify the nature of changes (added, modified, deleted) "
            "3. Identify potentially risky patterns or areas of concern "
            "Return a structured JSON with these fields: files (array of file data), risk_areas (array of concerns)"
        )
        
        # Use chunking to handle large diffs
        analysis_chunks = ai_client.chunk_analyze(
            system_prompt=system_prompt,
            content=diff,
            max_chunk_size=30000,
            temperature=0.2,
            json_response=True
        )
        
        # Process results
        all_files = []
        all_risks = []
        
        for chunk in analysis_chunks:
            try:
                chunk_data = json.loads(chunk)
                all_files.extend(chunk_data.get("files", []))
                all_risks.extend(chunk_data.get("risk_areas", []))
            except json.JSONDecodeError:
                logger.warning("Failed to parse analysis chunk as JSON")
                continue
        
        # Remove duplicates based on filename
        unique_files = {}
        for file in all_files:
            filename = file.get("filename")
            if filename and filename not in unique_files:
                unique_files[filename] = file
        
        # Deduplicate risks based on description
        unique_risks = {}
        for risk in all_risks:
            desc = risk.get("description", "")
            if desc and desc not in unique_risks:
                unique_risks[desc] = risk
        
        logger.info(f"Change analysis complete. Found {len(unique_files)} changed files and {len(unique_risks)} risk areas.")
        return {
            **state, 
            "file_changes": list(unique_files.values()),
            "issues": list(unique_risks.values())
        }
    except Exception as e:
        logger.error(f"Error analyzing changes: {str(e)}")
        # Continue with the process even if analysis fails
        return {
            **state,
            "file_changes": [],
            "issues": [],
        }

def analyze_files_in_parallel(state: ReviewState) -> ReviewState:
    """Analyze individual files in parallel for more detailed insights"""
    if state.get("error") or not state.get("diff"):
        return state
        
    file_changes = state.get("file_changes", [])
    if not file_changes:
        logger.info("No file changes to analyze in detail")
        return state
    
    logger.info(f"Analyzing {len(file_changes)} files in parallel")
    
    # Get AI client from options or create a new one
    ai_client = state.get("options", {}).get("ai_client") or AIClient(
        api_key=settings.AZURE_OPENAI_KEY,
        endpoint=settings.AZURE_OPENAI_ENDPOINT,
        deployment=settings.AZURE_OPENAI_DEPLOYEMENT_NAME
    )
    
    diff = state.get("diff")
    
    # Extract file-specific diffs
    file_diffs = {}
    current_file = None
    current_content = []
    
    for line in diff.split('\n'):
        if line.startswith('diff --git'):
            if current_file:
                file_diffs[current_file] = '\n'.join(current_content)
            file_match = re.search(r'b/(.*?)$', line)
            current_file = file_match.group(1) if file_match else None
            current_content = [line]
        elif current_file:
            current_content.append(line)
    
    if current_file:
        file_diffs[current_file] = '\n'.join(current_content)
    
    # Define analysis function for each file
    def analyze_file(file_info):
        filename = file_info.get("filename")
        file_diff = file_diffs.get(filename)
        if not file_diff:
            return file_info
        
        system_prompt = (
            "You are a code analysis expert. Analyze this file diff to identify:"
            "1. Specific code quality issues"
            "2. Potential bugs or edge cases"
            "3. Security considerations"
            "4. Performance implications"
            "Return a JSON with these fields: issues (array), improvements (array)"
        )
        
        try:
            analysis = ai_client.analyze_text(
                system_prompt=system_prompt,
                user_content=f"File: {filename}\n\n{file_diff}",
                temperature=0.2,
                json_response=True
            )
            
            analysis_data = json.loads(analysis)
            return {
                **file_info,
                "detailed_issues": analysis_data.get("issues", []),
                "suggested_improvements": analysis_data.get("improvements", [])
            }
        except Exception as e:
            logger.warning(f"Failed to analyze file {filename}: {str(e)}")
            return file_info
    
    # Use up to 5 workers for parallel processing
    enhanced_files = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(analyze_file, file) for file in file_changes[:10]]  # Limit to 10 most important files
        for future in concurrent.futures.as_completed(futures):
            try:
                enhanced_files.append(future.result())
            except Exception as e:
                logger.error(f"Error in file analysis thread: {str(e)}")
    
    # Merge remaining files
    file_map = {f.get("filename"): f for f in enhanced_files}
    for file in file_changes:
        filename = file.get("filename")
        if filename not in file_map:
            enhanced_files.append(file)
    
    logger.info(f"Detailed file analysis complete for {len(enhanced_files)} files")
    return {**state, "file_changes": enhanced_files}

def generate_recommendations(state: ReviewState) -> ReviewState:
    """Generate specific recommendations based on the code changes"""
    if state.get("error"):
        return state
        
    file_changes = state.get("file_changes", [])
    issues = state.get("issues", [])
    
    logger.info("Generating detailed recommendations")
    
    # Get AI client from options or create a new one
    ai_client = state.get("options", {}).get("ai_client") or AIClient(
        api_key=settings.AZURE_OPENAI_KEY,
        endpoint=settings.AZURE_OPENAI_ENDPOINT,
        deployment=settings.AZURE_OPENAI_DEPLOYEMENT_NAME
    )
    
    try:
        # Format the context for the AI
        file_context = "\n".join([f"- {f.get('filename', 'Unknown')}: {f.get('change_type', 'modified')}" 
                                 for f in file_changes[:10]])  # Limit to first 10 files
                                 
        # Include detailed issues if available
        detailed_issues = []
        for file in file_changes:
            file_issues = file.get("detailed_issues", [])
            if file_issues:
                filename = file.get("filename", "Unknown file")
                for issue in file_issues[:2]:  # Limit to 2 issues per file
                    detailed_issues.append(f"- {filename}: {issue}")
        
        # Include general issues
        general_issues = [f"- {issue.get('description', 'Issue')}" for issue in issues[:5]]
        
        all_issues = detailed_issues + general_issues
        issue_context = "\n".join(all_issues[:10])  # Limit total issues to 10
        
        # Generate recommendations based on reviews
        system_prompt = (
            "You are an expert code reviewer who provides specific, actionable recommendations. "
            "Focus on code quality, performance, security, and best practices. "
            "Each recommendation should be clear, specific, and actionable."
        )
        
        user_content = (
            f"Based on these code changes:\n\nFiles changed:\n{file_context}\n\n"
            f"Potential issues:\n{issue_context}\n\n"
            f"Generate 3-5 specific, actionable recommendations to improve this code."
        )
        
        recommendations_text = ai_client.analyze_text(
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.3
        )
        
        recommendations = recommendations_text.split("\n")
        # Clean up recommendations - remove numbering and empty entries
        clean_recommendations = []
        for rec in recommendations:
            rec = re.sub(r"^\d+\.\s*", "", rec).strip()
            if rec:
                clean_recommendations.append(rec)
        
        logger.info(f"Generated {len(clean_recommendations)} recommendations")
        return {**state, "recommendations": clean_recommendations}
    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}")
        return {**state, "recommendations": []}

def create_review(state: ReviewState) -> ReviewState:
    """Create the final review content"""
    if state.get("error"):
        logger.warning(f"Creating error review due to: {state.get('error')}")
        return {**state, "review": f"Error during review: {state.get('error')}"}
        
    diff = state.get("diff")
    file_changes = state.get("file_changes", [])
    issues = state.get("issues", [])
    recommendations = state.get("recommendations", [])
    is_commit = state.get("is_commit")
    review_template = state.get("review_template")
    
    logger.info("Creating comprehensive review")
    
    # Get AI client from options or create a new one
    ai_client = state.get("options", {}).get("ai_client") or AIClient(
        api_key=settings.AZURE_OPENAI_KEY,
        endpoint=settings.AZURE_OPENAI_ENDPOINT,
        deployment=settings.AZURE_OPENAI_DEPLOYEMENT_NAME
    )
    
    try:
        # Format some context for the AI
        file_summary = f"{len(file_changes)} files modified" if file_changes else "Unknown number of files modified"
        issue_count = len(issues)
        
        # Format recommendations as markdown list
        rec_text = "\n".join([f"- {rec}" for rec in recommendations]) if recommendations else "No specific recommendations."
        
        # Create detailed file analysis based on available info
        file_analysis = []
        for file in file_changes[:5]:  # Limit to 5 most important files
            filename = file.get("filename", "Unknown")
            change_type = file.get("change_type", "modified")
            
            file_entry = f"### {filename} ({change_type})\n"
            
            # Add detailed issues if available
            detailed_issues = file.get("detailed_issues", [])
            if detailed_issues:
                file_entry += "**Issues:**\n"
                for issue in detailed_issues[:3]:  # Limit to 3 issues per file
                    file_entry += f"- {issue}\n"
            
            # Add improvement suggestions if available
            improvements = file.get("suggested_improvements", [])
            if improvements:
                file_entry += "**Suggested improvements:**\n"
                for imp in improvements[:3]:  # Limit to 3 improvements per file
                    file_entry += f"- {imp}\n"
                    
            file_analysis.append(file_entry)
        
        file_analysis_text = "\n".join(file_analysis)
        
        # Provide context to the AI
        context = (
            f"This is a {'commit' if is_commit else 'pull request'} review.\n"
            f"Summary: {file_summary}, {issue_count} potential issues identified.\n"
            f"Key recommendations:\n{rec_text}\n\n"
            f"Detailed file analysis:\n{file_analysis_text}\n\n"
        )
        
        # Use the custom template if provided, otherwise use default
        if review_template:
            system_prompt = (
                "You are a senior software engineer reviewing code changes. "
                f"Use the following template for your review:\n\n{review_template}"
            )
        else:
            system_prompt = (
                "You are a senior software engineer reviewing code changes. Your review should be:"
                "1. Constructive and specific"
                "2. Organized by file when appropriate"
                "3. Include both positive feedback and areas for improvement"
                "4. Mention specific code patterns and best practices"
                "5. Written in markdown format with appropriate headers and code blocks"
            )
        
        # Use chunking to handle large diffs
        user_content = (
            f"Context about the changes:\n{context}\n\n"
            f"Here is the diff to review:\n{diff[:30000] if len(diff) > 30000 else diff}\n\n"
            f"Please provide a comprehensive code review."
        )
        
        review_content = ai_client.analyze_text(
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.4
        )
        
        logger.info(f"Review generated successfully: {len(review_content)} characters")
        return {**state, "review": review_content}
    except Exception as e:
        logger.error(f"Error generating review: {str(e)}")
        error_message = f"Error generating review: {str(e)}"
        return {**state, "error": error_message, "review": error_message}

def create_review_summary(state: ReviewState) -> ReviewState:
    """Create a concise summary of the review"""
    if state.get("error") or not state.get("review"):
        return state
        
    logger.info("Generating review summary")
    
    # Get AI client from options or create a new one
    ai_client = state.get("options", {}).get("ai_client") or AIClient(
        api_key=settings.AZURE_OPENAI_KEY,
        endpoint=settings.AZURE_OPENAI_ENDPOINT,
        deployment=settings.AZURE_OPENAI_DEPLOYEMENT_NAME
    )
    
    try:
        review = state.get("review")
        recommendations = state.get("recommendations", [])
        
        system_prompt = (
            "You are a technical writer creating a concise executive summary of a code review. "
            "Focus on the most important points and key recommendations."
        )
        
        user_content = (
            f"Here is the full code review:\n\n{review[:10000]}\n\n"
            f"Key recommendations identified:\n{', '.join(recommendations)}\n\n"
            f"Create a concise executive summary (3-5 bullet points) highlighting the most important aspects of this review."
        )
        
        summary = ai_client.analyze_text(
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.3
        )
        
        logger.info("Review summary generated successfully")
        return {**state, "review_summary": summary}
    except Exception as e:
        logger.error(f"Error generating review summary: {str(e)}")
        return state

def pr_review_agent(
    github_url: str, 
    github_token: str = None, 
    review_template: str = None,
    include_summary: bool = True,
    include_file_details: bool = True,
) -> Dict[str, Any]:
    """
    Review a GitHub PR or commit and provide AI-generated code review comments.
    Uses a multi-stage LangGraph approach with improved analysis capabilities.
    
    Args:
        github_url: URL to the GitHub PR or commit
        github_token: GitHub API token for authentication
        review_template: Custom template for review formatting
        include_summary: Whether to include a concise summary
        include_file_details: Whether to include detailed file analysis
        
    Returns:
        Dictionary containing the review text and metadata
    """
    # Set up logging
    logger.info(f"Starting code review for: {github_url}")

    try:
        # Initialize Azure OpenAI client
        logger.info("Initializing Azure OpenAI client")
        try:
            ai_client = AIClient(
                api_key=settings.AZURE_OPENAI_KEY,
                endpoint=settings.AZURE_OPENAI_ENDPOINT,
                deployment=settings.AZURE_OPENAI_DEPLOYEMENT_NAME
            )
            logger.info("Azure OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI client: {str(e)}")
            raise RuntimeError(f"Azure OpenAI client initialization failed: {str(e)}")

        # Build LangGraph workflow
        logger.info("Building and compiling LangGraph workflow")
        try:
            # Create StateGraph with our typed state
            builder = StateGraph(ReviewState)
            
            # Add nodes for each processing step
            builder.add_node("parse_url", parse_url)
            builder.add_node("fetch_content", fetch_content)
            builder.add_node("analyze_changes", analyze_changes)
            
            # Conditionally add detailed file analysis
            if include_file_details:
                builder.add_node("analyze_files_in_parallel", analyze_files_in_parallel)
                
            builder.add_node("generate_recommendations", generate_recommendations)
            builder.add_node("create_review", create_review)
            
            # Conditionally add summary generation
            if include_summary:
                builder.add_node("create_review_summary", create_review_summary)
            
            # Define the workflow
            builder.set_entry_point("parse_url")
            builder.add_edge("parse_url", "fetch_content")
            
            # Add conditional logic to skip analysis if there's an error
            builder.add_conditional_edges(
                "fetch_content",
                lambda state: "create_review" if state.get("error") else "analyze_changes"
            )
            
            builder.add_edge("analyze_changes", 
                            "analyze_files_in_parallel" if include_file_details else "generate_recommendations")
            
            if include_file_details:
                builder.add_edge("analyze_files_in_parallel", "generate_recommendations")
                
            builder.add_edge("generate_recommendations", "create_review")
            
            if include_summary:
                builder.add_edge("create_review", "create_review_summary")
                builder.add_edge("create_review_summary", END)
            else:
                builder.add_edge("create_review", END)
            
            # Compile the graph
            graph = builder.compile()
            logger.info("LangGraph compiled successfully")
        except Exception as e:
            logger.error(f"Failed to build LangGraph: {str(e)}")
            raise RuntimeError(f"LangGraph compilation failed: {str(e)}")

        # Execute the graph
        logger.info("Executing LangGraph to generate review")
        try:
            # Initialize state with the URL and options
            initial_state = {
                "url": github_url, 
                "issues": [], 
                "recommendations": [],
                "review_template": review_template,
                "options": {
                    "github_token": github_token,
                    "ai_client": ai_client
                }
            }
            output = graph.invoke(initial_state)
            logger.info("LangGraph execution completed successfully")
        except Exception as e:
            logger.error(f"Error during LangGraph execution: {str(e)}")
            raise RuntimeError(f"LangGraph execution failed: {str(e)}")

        # Process results
        if "review" not in output:
            logger.error("Review output not found in LangGraph result")
            raise ValueError("No review content was generated")

        # Prepare result object
        result = {
            "review": output.get("review", ""),
            "review_type": "commit" if output.get("is_commit", False) else "PR",
            "recommendations": output.get("recommendations", [])
        }
        
        # Add summary if generated
        if include_summary and "review_summary" in output:
            result["summary"] = output.get("review_summary", "")
            
        # Add metadata
        result["metadata"] = {
            "files_changed": len(output.get("file_changes", [])),
            "issues_found": len(output.get("issues", [])),
            "url": github_url
        }
        
        review_type = result["review_type"]
        logger.info(f"{review_type} review completed successfully. Review length: {len(result['review'])} characters")
        
        if not output.get("error"):
            print(f"\n--- AI {review_type.upper()} Review Comments ---\n")
            print(result["review"])
            
            if include_summary and "summary" in result:
                print("\n--- Summary ---\n")
                print(result["summary"])
        else:
            print(f"\n--- Error during {review_type.upper()} review ---\n")
            print(output.get("error"))
            
        return result

    except Exception as e:
        # Catch and log any unhandled exceptions
        logger.error(f"Unhandled exception in review agent: {str(e)}")
        logger.error(traceback.format_exc())
        # Return error information
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "url": github_url
        }