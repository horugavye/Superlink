#!/usr/bin/env python3
import os
import sys
import signal
import logging
import argparse
from pathlib import Path
import uvicorn
from django.core.management import execute_from_command_line
from superlink.settings import SERVER_SETTINGS, PROCESS_MANAGEMENT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/server.log')
    ]
)
logger = logging.getLogger(__name__)

def create_required_directories():
    """Create required directories if they don't exist"""
    directories = ['logs', 'media', 'static']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)

def handle_signal(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    sys.exit(0)

def main():
    """Main function to run the server"""
    parser = argparse.ArgumentParser(description='Run the Django server with proper process management')
    parser.add_argument('--host', default=SERVER_SETTINGS['HOST'], help='Host to bind to')
    parser.add_argument('--port', type=int, default=SERVER_SETTINGS['PORT'], help='Port to bind to')
    parser.add_argument('--workers', type=int, default=SERVER_SETTINGS['WORKERS'], help='Number of worker processes')
    parser.add_argument('--threads', type=int, default=SERVER_SETTINGS['THREADS'], help='Number of threads per worker')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload')
    args = parser.parse_args()

    # Create required directories
    create_required_directories()

    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Configure uvicorn
    config = uvicorn.Config(
        "superlink.asgi:application",
        host=args.host,
        port=args.port,
        workers=args.workers,
        loop="uvloop",
        http="httptools",
        ws="websockets",
        lifespan="on",
        log_level="info",
        access_log=True,
        use_colors=True,
        reload=args.reload,
        reload_dirs=["."],
        worker_class=PROCESS_MANAGEMENT['WORKER_CLASS'],
        limit_concurrency=SERVER_SETTINGS['LIMIT_CONCURRENCY'],
        limit_max_requests=SERVER_SETTINGS['LIMIT_MAX_REQUESTS'],
        timeout_keep_alive=SERVER_SETTINGS['TIMEOUT_KEEP_ALIVE'],
        graceful_shutdown_timeout=SERVER_SETTINGS['GRACEFUL_SHUTDOWN_TIMEOUT'],
    )

    # Run migrations
    logger.info("Running migrations...")
    execute_from_command_line(['manage.py', 'migrate'])

    # Collect static files
    logger.info("Collecting static files...")
    execute_from_command_line(['manage.py', 'collectstatic', '--noinput'])

    # Start the server
    logger.info(f"Starting server on {args.host}:{args.port} with {args.workers} workers")
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    main() 