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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Import your converter module
from converter import convert_file

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
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


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


def process_file_sync(input_path: Path, output_path: Path):
    logger.debug(f"Starting conversion from {input_path} to {output_path}")
    try:
        # Call CPU-heavy file processing (synchronous) conversion function
        convert_file(input_path, output_path)
        logger.debug(f"Conversion completed, output at {output_path}")
        logger.debug(f"Output file exists: {os.path.exists(output_path)}")
    except Exception as e:
        logger.error(f"Conversion failed with error: {str(e)}")
        raise


@app.post("/convert")
@limiter.limit("5/minute")  # Rate limit: 5 file uploads per minute
async def convert(
    request: Request,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
    # Check if file exists
    if not file:
        raise HTTPException(status_code=400, detail="No file part")

    # Check if filename is empty
    if file.filename == "":
        raise HTTPException(status_code=400, detail="No selected file")

    # Check file extension
    if not allowed_file(file.filename):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Only XML files are accepted."
        )

    # Validate file size
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large (max 50 MB)")

    safe_file_name = secure_filename(file.filename)
    safe_file_path = Path(safe_file_name)  # Create Path object once

    # Generate unique input path using a temporary file
    # Suffix from the original (secured) filename
    input_suffix = safe_file_path.suffix
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=input_suffix, dir=UPLOAD_DIR
    ) as tmp_input_file:
        input_path = Path(tmp_input_file.name)
        # Use await for async file operations if available, otherwise stick to sync shutil
        # For large files, consider async streaming if shutil becomes a bottleneck
        shutil.copyfileobj(file.file, tmp_input_file)

    # Define output path based on the *original* (secured) filename stem
    # Output file will be in the same temp directory as the input
    output_filename = f"{safe_file_path.stem}.json"
    output_path = input_path.with_name(output_filename)

    try:
        # Run conversion in a thread pool to avoid blocking the event loop
        await run_in_threadpool(
            process_file_sync, input_path=input_path, output_path=output_path
        )

        if not output_path.exists():  # Use Path object's exists()
            raise HTTPException(
                status_code=500, detail="Conversion failed, output file not created."
            )

        # Schedule cleanup for BOTH input and output files using BackgroundTasks
        cleanup_tasks = BackgroundTasks()
        cleanup_tasks.add_task(cleanup_file, file_path=input_path)
        cleanup_tasks.add_task(cleanup_file, file_path=output_path)

        # Return the converted file
        return FileResponse(
            path=str(output_path),
            filename=output_filename,  # Use the meaningful filename
            media_type="application/json",
            background=cleanup_tasks,  # Pass the tasks object
        )
    except Exception as e:
        # Clean up temporary files immediately on error
        # Use a separate function or call cleanup_file twice if it only handles one path
        cleanup_file(input_path)
        if output_path.exists():  # Clean up output if it was partially created
            cleanup_file(output_path)
        logger.error(f"Error processing file {safe_file_name}: {str(e)}")
        raise HTTPException(500, f"Error processing file {safe_file_name}: {str(e)}")


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
        "main:app", host="0.0.0.0", port=5000, reload=True
    )  # This is for local testing
