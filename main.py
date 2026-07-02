import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from werkzeug.utils import secure_filename

from converter import convert_file

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create a limiter instance with a function to get the client's IP address
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="BMEcat to ETIM xChange Converter")
# Add rate limit exceeded handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

BASE_DIR = Path(__file__).parent
# Set up templates directory
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# Mount static files directory
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# Define temp directory for file uploads
UPLOAD_DIR = Path(tempfile.gettempdir())
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024


def allowed_file(filename: str) -> bool:
    # Case-insensitive check for .xml extension
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "xml"


async def save_upload_file(file: UploadFile, suffix: str) -> Path:
    input_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, dir=UPLOAD_DIR
        ) as tmp_input_file:
            input_path = Path(tmp_input_file.name)
            bytes_written = 0

            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                bytes_written += len(chunk)
                if bytes_written > MAX_FILE_SIZE:
                    raise HTTPException(
                        413,
                        f"File too large (max {MAX_FILE_SIZE // (1024 * 1024)} MB)",
                    )
                tmp_input_file.write(chunk)

        return input_path
    except Exception:
        cleanup_file(input_path)
        raise


@app.get("/", response_class=HTMLResponse)
@limiter.limit("10/minute")  # Rate limit: 10 requests per minute
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health")
async def health_check():
    # Perform checks (e.g., database connection, external services)
    all_systems_operational = True
    if all_systems_operational:
        return JSONResponse(content={"status": "healthy"}, status_code=200)
    else:
        return JSONResponse(content={"status": "unhealthy"}, status_code=503)


# Create a semaphore to limit concurrent conversions to 2
CONVERSION_SEMAPHORE = asyncio.Semaphore(2)


@app.post("/convert")
@limiter.limit("5/minute")
async def convert(request: Request, file: UploadFile = File(...)):
    # Check if filename is empty or missing
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    # Check file extension
    if not allowed_file(file.filename):
        raise HTTPException(400, "Invalid file type. Only XML files are accepted.")

    # Validate file size
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            400, f"File too large (max {MAX_FILE_SIZE // (1024 * 1024)} MB)"
        )

    safe_file_name = Path(secure_filename(file.filename))
    if not safe_file_name.name or safe_file_name.suffix.lower() != ".xml":
        raise HTTPException(400, "Invalid file name.")

    output_filename = f"{safe_file_name.stem}.json"
    input_path: Optional[Path] = None
    output_path: Optional[Path] = None

    try:
        input_path = await save_upload_file(file, safe_file_name.suffix)
        output_path = input_path.with_suffix(".json")

        # Acquire semaphore before starting the threadpool task
        async with CONVERSION_SEMAPHORE:
            logger.debug(
                f"Acquired semaphore for {safe_file_name}. Running conversion."
            )
            logger.debug(f"Starting conversion from {input_path} to {output_path}")
            # Run conversion in a thread pool to avoid blocking the event loop
            await run_in_threadpool(convert_file, input_path, output_path)
            logger.debug(f"Conversion completed, output at {output_path}")
            logger.debug(f"Output file exists: {output_path.exists()}")
            logger.debug(f"Conversion OK for {safe_file_name}. Releasing semaphore.")

        # Check if output exists *after* the conversion task is done
        if not output_path.is_file() or output_path.stat().st_size == 0:
            logger.error(
                f"Conversion failed: Output file {output_path} is missing or empty."
            )
            raise HTTPException(
                status_code=500,
                detail="Conversion failed because no output file was created.",
            )

        # --- Add logging to check file content ---
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                # Log the first 200 characters to check if it looks like JSON
                content_preview = f.read(200)
                logger.debug(f"Output file preview ({output_path}): {content_preview}")
                # Optional: Add more robust JSON validation if needed
                # import json
                # f.seek(0) # Reset file pointer
                # json.load(f) # Try to parse the whole file
        except Exception as read_err:
            logger.error(
                f"Error reading or validating output file {output_path}: {read_err}"
            )
            raise HTTPException(
                status_code=500,
                detail="Conversion produced an invalid or unreadable output file.",
            )
        # --- End of added logging ---

        # Schedule cleanup for BOTH input and output files using BackgroundTasks
        cleanup_tasks = BackgroundTasks()
        cleanup_tasks.add_task(cleanup_file, file_path=input_path)
        cleanup_tasks.add_task(cleanup_file, file_path=output_path)

        # Return the converted file
        return FileResponse(
            path=str(output_path),
            filename=output_filename,
            media_type="application/json",
            background=cleanup_tasks,
        )

    except HTTPException:
        cleanup_file(input_path)
        cleanup_file(output_path)
        raise
    except Exception as e:
        # Cleanup is handled here if an exception occurs *outside* the semaphore block
        # or if run_in_threadpool itself raises an exception.
        cleanup_file(input_path)
        cleanup_file(output_path)
        logger.error(f"Error processing file {safe_file_name}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"XML conversion failed. Maybe it is not a (properly formatted) BMEcat? ({str(e)})"
            },
        )
    finally:
        await file.close()


def cleanup_file(file_path: Optional[Path]):
    try:
        if file_path and file_path.exists():
            file_path.unlink()
            logger.debug(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {e}")
        # Log error but don't raise to avoid crashing background task


if __name__ == "__main__":
    uvicorn.run(
        "main:app", host="localhost", port=5000, reload=True
    )  # This is for local testing
