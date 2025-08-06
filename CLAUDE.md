# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BMEcat to ETIM xChange Converter** - A web application that converts BMEcat XML product catalogs to ETIM xChange JSON format. This is a defensive tool for data format conversion in the electrical/electronics industry.

## Architecture

### Core Components

- **main.py:1-190** - FastAPI web server with file upload, rate limiting, and health checks
- **converter.py:1-1223** - XML to JSON conversion engine using lxml for XML parsing and orjson for JSON output
- **Dockerfile:1-36** - Multi-stage Alpine-based container with Rust dependencies for performance
- **templates/index.html:1-193** - Single-page web interface with drag-and-drop file upload

### Key Technologies

- **Backend**: FastAPI with async support, rate limiting via slowapi
- **XML Processing**: lxml with entity resolution disabled for security
- **JSON**: orjson for high-performance JSON serialization
- **Validation**: jsonschema-rs for ETIM xChange schema validation
- **Deployment**: Docker with health checks via curl

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run local development server
python main.py
# or
uvicorn main:app --host localhost --port 5000 --reload
```

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up --build

# Access application at http://localhost:5001
```

### Testing & Validation
```bash
# Manual testing with curl
curl -X POST -F "file=@test_catalog.xml" http://localhost:5001/convert

# Health check
curl http://localhost:5001/health

# Validate JSON output against schema
python -c "from converter import validate_json; validate_json('output.json', 'xChange_Schema_V1.1-2024-08-23.json')"
```

## File Structure

```
BMEcat-2-ETIMxChange/
├── main.py                 # FastAPI web server
├── converter.py            # XML to JSON conversion logic
├── requirements.txt        # Python dependencies
├── Dockerfile             # Container configuration
├── docker-compose.yaml    # Service orchestration
├── xChange_Schema_V1.1-2024-08-23.json  # ETIM validation schema
├── templates/
│   └── index.html         # Web interface
└── static/
    └── css/
        └── style.css      # Styling
```

## Key Features

### Conversion Logic
- **XML Processing**: Removes namespaces and processes BMEcat structure
- **ETIM Mapping**: Converts ISO 639-2 language codes to language-region format
- **Attachment Mapping**: Maps BMEcat MIME codes to ETIM xChange attachment types
- **Product Relations**: Handles product references and relation types
- **Validation**: Validates output against official ETIM xChange schema

### Security & Performance
- **Rate Limiting**: 5 conversions/minute, 10 requests/minute via slowapi
- **File Size**: 100MB maximum file size
- **Concurrent Processing**: Limited to 2 simultaneous conversions via semaphore
- **Cleanup**: Automatic temp file cleanup via BackgroundTasks
- **Entity Resolution**: Disabled in XML parser to prevent XXE attacks

## Configuration

### Environment Variables
- **Port**: 5001 (Docker), 5000 (local)
- **Upload Directory**: Uses system temp directory
- **Max File Size**: 100MB

### Rate Limits
- Index page: 10 requests/minute
- Conversion endpoint: 5 requests/minute
- Concurrent conversions: 2 maximum

## Production Deployment

The application is deployed at https://converter.classifast.com/ with the following characteristics:
- Stateless design - no persistent data storage
- Automatic cleanup of uploaded files
- Health check endpoint at `/health`
- Docker-based deployment with restart policies

## Common Development Tasks

### Adding New Field Mappings
Edit `converter.py:320-513` for attachment type mappings and relation type mappings.

### Schema Updates
Replace `xChange_Schema_V1.1-2024-08-23.json` with new ETIM schema versions.

### Testing Large Catalogs
Use the validation function in converter.py to test against the official schema after processing large files.

### Performance Optimization
The converter uses Rust-based libraries (orjson, jsonschema-rs) for maximum performance with large catalogs.