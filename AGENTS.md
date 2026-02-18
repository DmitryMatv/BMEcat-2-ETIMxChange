# AGENTS.md - Coding Agent Guidelines

## Project Overview

BMEcat to ETIM xChange converter - a Python FastAPI web application that converts BMEcat XML product catalogs to ETIM xChange JSON format.

## Build/Run/Test Commands

### Running the Application

```bash
# Development (local)
python main.py
# Runs on http://localhost:5000 with auto-reload

# Production (Docker)
docker-compose up --build
# Runs on port 5001

# Direct uvicorn
uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

### Installing Dependencies

```bash
pip install -r requirements.txt
```

### Testing

```bash
# No automated tests exist. Manual testing:
# 1. Start the server
# 2. Upload a BMEcat XML file via the web UI at /
# 3. Verify the output JSON is valid against xChange_Schema_V1.1-2024-08-23.json

# Test a single file conversion directly in Python:
python -c "from converter import convert_file; convert_file('input.xml', 'output.json')"
```

### Linting/Type Checking

```bash
# If available, use:
ruff check .
mypy main.py converter.py

# Install if needed:
pip install ruff mypy
```

### Docker Commands

```bash
docker build -t bmecat-converter .
docker run -p 5001:5001 bmecat-converter
```

## Code Style Guidelines

### Python Version

- Target: Python 3.13+
- Use modern Python features when appropriate

### Imports

```python
# Standard library first
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

# Third-party libraries second (alphabetically grouped)
import orjson
from fastapi import FastAPI, HTTPException
from lxml import etree
```

### Formatting

- Indentation: 4 spaces
- Line length: 120 characters max
- No trailing whitespace
- Use double quotes for strings

### Type Hints

- Use type hints for function signatures
- Use `Optional[T]` for optional parameters/returns
- Use `Path` from pathlib for file paths

```python
def convert_file(input_path: str, output_path: str) -> None:
def get_val(target_field: str, XML_root, val_type=str) -> Optional[str]:
```

### Naming Conventions

- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private functions: prefix with underscore if intended as internal
- XML variable names can use uppercase for clarity: `BMECAT`, `HEADER`, `CATALOG`

### Docstrings

Use Google-style docstrings:

```python
def function_name(arg1: str, arg2: int) -> bool:
    """Brief description of the function.

    Args:
        arg1: Description of arg1
        arg2: Description of arg2

    Returns:
        Description of return value

    Raises:
        ValueError: When arg1 is invalid
    """
```

### Error Handling

- FastAPI endpoints: Use `HTTPException` with appropriate status codes
- Use `raise HTTPException(status_code=400, detail="message")`
- Log errors with `logger.error()` before raising
- In converter.py: Use `print()` for progress messages, handle errors gracefully

```python
if not file:
    raise HTTPException(status_code=400, detail="No file part")
```

### Comments

- Do NOT add comments unless explicitly requested
- Code should be self-documenting through clear naming
- Docstrings are acceptable for public functions

### Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug(f"Processing {filename}")
logger.error(f"Error: {str(e)}")
```

### FastAPI Patterns

```python
# Route with rate limiting
@app.post("/convert")
@limiter.limit("5/minute")
async def convert(request: Request, file: UploadFile = File(...)):
    # Validation first
    if not file:
        raise HTTPException(status_code=400, detail="No file")

    # Process and return
    return FileResponse(path=str(output_path))
```

### XML Processing (lxml)

```python
# Use secure XML parsing
parser = etree.XMLParser(resolve_entities=False)
root = etree.parse(xml_path, parser).getroot()

# XPath queries
element = root.findtext(".//FIELD_NAME")
elements = root.xpath(".//ELEMENT[@attr='value']/text()")
```

### JSON Processing (orjson)

```python
# Reading
with open(path, "rb") as f:
    data = orjson.loads(f.read())

# Writing
with open(path, "wb") as f:
    f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
```

### File Paths

- Use `pathlib.Path` for all file operations
- Use `tempfile` for temporary files
- Always clean up temporary files after use

```python
from pathlib import Path
import tempfile

input_path = Path("/path/to/file.xml")
with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
    temp_path = Path(tmp.name)
```

### Async Patterns

```python
# Use semaphore for limiting concurrent operations
SEMAPHORE = asyncio.Semaphore(2)

async with SEMAPHORE:
    await run_in_threadpool(blocking_function, arg1, arg2)
```

## Project Structure

```
/
├── main.py              # FastAPI application, routes, upload handling
├── converter.py         # BMEcat to xChange conversion logic
├── requirements.txt     # Python dependencies
├── Dockerfile           # Multi-stage Docker build
├── docker-compose.yaml  # Docker Compose configuration
├── templates/
│   └── index.html       # Web UI template
├── static/
│   └── css/             # Stylesheets
└── xChange_Schema_V1.1-2024-08-23.json  # JSON schema for validation
```

## Key Dependencies

- **fastapi**: Web framework
- **uvicorn**: ASGI server
- **lxml**: XML parsing (secure config required)
- **orjson**: Fast JSON serialization
- **jsonschema-rs**: JSON schema validation
- **slowapi**: Rate limiting
- **werkzeug**: Secure filename handling

## Security Notes

- Always use `secure_filename()` for uploaded file names
- Disable XML entity resolution: `XMLParser(resolve_entities=False)`
- Validate file size before processing
- Clean up temporary files after response
