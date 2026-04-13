from fastapi import APIRouter

from app.api.v1.endpoints import ai_tools, auth, cover_letters, job_tracker, n8n_webhook, resumes

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["Resumes"])
api_router.include_router(cover_letters.router, prefix="/cover-letters", tags=["Cover Letters"])
api_router.include_router(ai_tools.router, prefix="/ai", tags=["AI Tools"])
api_router.include_router(job_tracker.router, prefix="/jobs", tags=["Job Tracker"])
api_router.include_router(n8n_webhook.router, prefix="/webhooks/n8n", tags=["n8n Webhooks"])
