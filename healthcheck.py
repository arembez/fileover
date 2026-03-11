#!/usr/bin/env python
"""
healthcheck.py

Docker health check script for FileOver microservice.
Runs comprehensive health checks and exits with appropriate code for container orchestration.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

import asyncio
import sys
import argparse
from app import health

def main():
    parser = argparse.ArgumentParser(description='Health check for FileOver service')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show detailed health status')
    args = parser.parse_args()
    
    try:
        result = asyncio.run(health.check_all())
        
        if args.verbose:
            print(result.model_dump_json(indent=2))
        else:
            # Quiet mode - just show summary
            print(f"Health status: {result.status}")
            if result.status != "healthy":
                print(f"Summary: {result.summary}")
        
        # Exit with 0 if healthy, 1 if unhealthy
        sys.exit(0 if result.status == "healthy" else 1)
    except Exception as e:
        print(f"Health check failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()