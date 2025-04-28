import os, tempfile, logging
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn


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
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def allowed_file(filename: str) -> bool:
    # Case-insensitive check for .xml extension
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "xml"


@app.get("/", response_class=HTMLResponse)
@limiter.limit("10/minute")  # Rate limit: 10 requests per minute
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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

    # Use secure_filename for better sanitization
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    
    input_path = os.path.join(UPLOAD_DIR, filename)
    output_filename = f"{os.path.splitext(filename)[0]}.json"
    output_path = os.path.join(UPLOAD_DIR, output_filename)

    try:
        # Save uploaded file (async)
        with open(input_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Run conversion synchronously instead of as a background task
        # This ensures the file is created before we check for it
        process_file_sync(input_path, output_path)
        # Run CPU-heavy task in a separate thread?

        # Check if the output file was created
        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=500, detail="Conversion failed, output file not created."
            )

        # Set up file cleanup for after response is sent
        background_tasks.add_task(cleanup_files, input_path, output_path)

        # Return the converted file
        return FileResponse(
            path=output_path, filename=output_filename, media_type="application/json"
        )

    except Exception as e:
        # Clean up on error
        cleanup_files(input_path, None)
        raise HTTPException(500, f"Error processing file: {str(e)}")


def cleanup_files(input_path, output_path=None):
    try:
        if input_path and os.path.exists(input_path):
            os.remove(input_path)
        # We only delete the output file if an error occurred
        # For normal execution, FastAPI will handle this after sending the response
    except Exception:
        pass


if __name__ == "__main__":
    uvicorn.run(
        "main:app", host="0.0.0.0", port=5000, reload=False
    )  # reload is useful during development
