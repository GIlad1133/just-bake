"""
Main entry point for Just Bake invoice automation.
Processes pending orders from Google Sheets and creates invoices via Keep.co.il API.
"""

import sys
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from .google_sheets import GoogleSheetsClient
from .keep_client import KeepClient
from .invoice_processor import InvoiceProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main workflow."""
    try:
        logger.info("=== Just Bake Invoice Automation Started ===")

        # Load environment variables from .env file (for local development)
        load_dotenv()

        # Initialize Google Sheets client
        logger.info("Initializing Google Sheets client")
        sheets_client = GoogleSheetsClient()

        # Initialize Keep.co.il client
        logger.info("Initializing Keep.co.il client")
        keep_client = KeepClient()

        # Create invoice processor
        processor = InvoiceProcessor(sheets_client, keep_client)

        # Check for date filter argument
        max_date = None
        if len(sys.argv) > 1:
            # Parse date argument (YYYY-MM-DD format)
            try:
                max_date = datetime.strptime(sys.argv[1], "%Y-%m-%d")
                logger.info(f"Date filter: Processing orders up to {max_date.date()}")
            except ValueError:
                logger.error(f"Invalid date format: {sys.argv[1]}. Use YYYY-MM-DD format.")
                sys.exit(1)

        # Process pending invoices
        logger.info("Processing pending invoices")
        summary = processor.process_pending_invoices(max_date=max_date)

        # Log summary
        logger.info("=== Processing Summary ===")
        logger.info(f"Total orders processed: {summary['total']}")
        logger.info(f"Successfully created: {summary['succeeded']}")
        logger.info(f"Failed: {summary['failed']}")

        # Exit with appropriate code
        if summary['failed'] > 0:
            logger.warning("Some orders failed to process")
            sys.exit(1)
        else:
            logger.info("All orders processed successfully")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
