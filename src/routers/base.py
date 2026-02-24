from fastapi import APIRouter


router = APIRouter(tags=["Base"])


@router.get("/")
async def base():
    """Base endpoint to check if the API is running."""
    return {"message": "GuardCore API is running."}
