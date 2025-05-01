import os, tempfile, logging
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
from werkzeug.utils import secure_filename
import shutil
import asyncio  # Add asyncio import

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


def allowed_file(filename: str) -> bool:
    # Case-insensitive check for .xml extension
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "xml"


@app.get("/", response_class=HTMLResponse)
@limiter.limit("10/minute")  # Rate limit: 10 requests per minute
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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

# Import your converter module
from converter import convert_file


@app.post("/convert")
@limiter.limit("5/minute")
async def convert(request: Request, file: UploadFile = File(...)):

    # Check if file exists
    if not file:
        raise HTTPException(status_code=400, detail="No file part")

    # Check if filename is empty
    if file.filename == "":
        raise HTTPException(status_code=400, detail="No selected file")

    # Check file extension
    if not allowed_file(file.filename):
        raise HTTPException(400, "Invalid file type. Only XML files are accepted.")

    # Validate file size
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            400, f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)"
        )

    # Create Path object at once
    safe_file_name = Path(secure_filename(file.filename))

    # Generate unique input path using a temporary file
    # Suffix from the secured filename
    input_suffix = safe_file_name.suffix
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=input_suffix, dir=UPLOAD_DIR
    ) as tmp_input_file:
        input_path = Path(tmp_input_file.name)
        # Use await for async file operations if available, otherwise stick to sync shutil
        # For large files, consider async streaming if shutil becomes a bottleneck
        shutil.copyfileobj(file.file, tmp_input_file)

    # Define output path based on the *secured* filename stem
    # Output file will be in the same temp directory as the input
    output_filename = f"{safe_file_name.stem}.json"
    output_path = input_path.with_name(output_filename)

    try:
        # Acquire semaphore before starting the threadpool task
        async with CONVERSION_SEMAPHORE:
            logger.debug(
                f"Acquired semaphore for {safe_file_name}. Running conversion."
            )
            logger.debug(f"Starting conversion from {input_path} to {output_path}")
            # Run conversion in a thread pool to avoid blocking the event loop
            await run_in_threadpool(convert_file, input_path, output_path)
            logger.debug(f"Conversion completed, output at {output_path}")
            logger.debug(f"Output file exists: {os.path.exists(output_path)}")
            logger.debug(f"Conversion OK for {safe_file_name}. Releasing semaphore.")

        # Check if output exists *after* the conversion task is done
        if not output_path.exists():
            logger.error(f"Conversion failed: Output file {output_path} not found.")
            raise HTTPException(
                status_code=500,
                detail="Conversion failed because no output file created.",
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

    except Exception as e:
        # Cleanup is handled here if an exception occurs *outside* the semaphore block
        # or if run_in_threadpool itself raises an exception.
        cleanup_file(input_path)
        if output_path.exists():
            cleanup_file(output_path)
        logger.error(f"Error processing file {safe_file_name}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"XML conversion failed. Maybe it is not a (properly formatted) BMEcat? ({str(e)})"
            },
        )


def cleanup_file(file_path: Path):
    try:
        if file_path and file_path.exists():
            os.remove(file_path)
            logger.debug(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {e}")
        # Log error but don't raise to avoid crashing background task


if __name__ == "__main__":
    uvicorn.run(
        "main:app", host="localhost", port=5000, reload=True
    )  # This is for local testing
