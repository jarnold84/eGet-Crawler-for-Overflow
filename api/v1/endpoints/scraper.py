from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt               # ← only the jose implementation
from loguru import logger

from core.config import settings
from models.request import ScrapeRequest
from models.response import ScrapeResponse

router = APIRouter(tags=["scraper"])
security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> bool:
    """
    Validate the supplied JWT. Returns ``True`` if the token is valid;
    otherwise raises a 401 HTTPException.
    """
    try:
        jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
        return True
    except JWTError:  # catches only jose‑specific JWT errors
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_url(request: ScrapeRequest, req: Request):
    try:
        logger.info(f"Processing scrape request for URL: {request.url}")
        
        # Check if scraper exists in app state
        if not hasattr(req.app.state, "scraper"):
            logger.error("Scraper not initialized in app state")
            raise HTTPException(
                status_code=500,
                detail="Scraper service not initialized"
            )

        options = {
            "only_main": request.onlyMainContent,
            "timeout": request.timeout or settings.TIMEOUT,
            "user_agent": settings.DEFAULT_USER_AGENT,
            "headers": request.headers,
            "include_screenshot": request.includeScreenshot,
            "include_raw_html": request.includeRawHtml,
            "screenshot_quality": settings.SCREENSHOT_QUALITY,
            "wait_for_selector": request.waitFor
        }
        
        if request.actions:
            options["actions"] = request.actions

        logger.debug(f"Scraping with options: {options}")
        
        result = await req.app.state.scraper.scrape(str(request.url), options)
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Scraping failed - no result returned"
            )
            
        return result
        
    except Exception as e:
        logger.exception(f"Scraping error: {str(e)}")  # This will log the full traceback
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed: {str(e)}"
        )
