from fastapi import FastAPI
from api.endpoints import router

# Create FastAPI app
app = FastAPI(title="OpenAI Celery API")

# Include routers
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)