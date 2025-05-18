from fastapi import HTTPException, APIRouter, status
from celery.result import AsyncResult
from celery_app import celery_app
from tasks.task import run_pr_review
import traceback
from typing import Dict, Any
from core.models import PRReviewRequest, TaskResponse

router = APIRouter()

@router.post("/api/analyze-pr", response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
def review_pr(request: PRReviewRequest) -> Dict[str, str]:
    try:
        task = run_pr_review.delay(request.pr_url, request.github_token or "")
        return {"task_id": task.id, "status": "processing", "message": "PR review task created"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create task: {str(e)}"
        )


def get_task_info(task_id: str) -> TaskResponse:
    """Helper function to get task information with consistent error handling"""
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        try:
            task_status = task_result.status
        except Exception as e:
            print(f"Error getting task status: {str(e)}")
            task_status = "UNKNOWN"

        # Prepare the response
        response = {
            "task_id": task_id,
            "status": task_status,
        }

        # Add additional info based on task state
        if task_status == 'PENDING':
            response["message"] = "Task is pending execution"
        elif task_status == 'PROGRESS':
            # Safely get info
            try:
                info = task_result.info or {}
                response["message"] = info.get('status', 'Task is in progress')
            except:
                response["message"] = "Task is in progress"
        elif task_status == 'SUCCESS':
            response["message"] = "Task completed successfully"
            if task_id.strip():  # Only try to get result if we have a valid task_id
                try:
                    response["result"] = task_result.result
                except Exception as e:
                    print(f"Error getting task result: {str(e)}")
                    response["message"] = f"Task completed but error retrieving result: {str(e)}"
        elif task_status == 'FAILURE':
            # Safely get error info
            try:
                error = str(task_result.result) if task_result.result else "Unknown error"
                response["message"] = f"Task failed: {error}"
                response["error"] = error
            except:
                response["message"] = "Task failed with unknown error"
                response["error"] = "Could not retrieve error details"
        else:
            response["message"] = f"Task status: {task_status}"

        return response
    except Exception as e:
        print(f"Error getting task info: {str(e)}")
        print(traceback.format_exc())
        return {
            "task_id": task_id,
            "status": "ERROR",
            "message": f"Error retrieving task information: {str(e)}"
        }


@router.get("/api/status/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str) -> Dict[str, Any]:
    return get_task_info(task_id)


@router.get("/api/results/{task_id}", response_model=TaskResponse)
async def get_task_result(task_id: str) -> Dict[str, Any]:
    response = get_task_info(task_id)
    
    # Additional validation specific to results endpoint
    if response["status"] != 'SUCCESS' and "result" not in response:
        response["message"] = "Task is not completed yet or failed"
        response["result"] = None
        
    return response


@router.get("/", response_model=Dict[str, str])
async def root() -> Dict[str, str]:
    return {"status": "API is running", "message": "OpenAI Celery API is operational"}