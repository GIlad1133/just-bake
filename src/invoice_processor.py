"""
Invoice processing business logic.
Orchestrates the workflow of reading orders, creating invoices, and updating status.
"""

from typing import List, Tuple, Optional
from datetime import datetime
from .models import Order, KeepReceipt, KeepReceiptItem
from .google_sheets import GoogleSheetsClient
from .keep_client import KeepClient
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InvoiceProcessor:
    """Processes pending orders and creates Keep.co.il invoices."""

    def __init__(self, sheets_client: GoogleSheetsClient, keep_client: KeepClient):
        """
        Initialize invoice processor.

        Args:
            sheets_client: Google Sheets client
            keep_client: Keep.co.il API client
        """
        self.sheets = sheets_client
        self.keep = keep_client

    def _build_receipt(self, order: Order) -> KeepReceipt:
        """
        Transform Order to KeepReceipt.

        Args:
            order: Order from Google Sheets

        Returns:
            KeepReceipt ready for API submission
        """
        # Convert order items to Keep receipt items
        receipt_items = [
            KeepReceiptItem(
                name=item.name,
                quantity=item.quantity,
                price=int(round(item.price_per_unit * 100))  # Convert to agorot
            )
            for item in order.items
        ]

        # Build payment method comment
        payment_comment = f"תשלום ב{order.payment_method}"

        # Create receipt
        receipt = KeepReceipt(
            customer_name=order.customer_name,
            doc_date=order.order_date,
            items=receipt_items,
            total_amount=order.total_agorot,
            payment_method_comment=payment_comment,
            phone=order.phone,
            business_id=order.business_id
        )

        return receipt

    def _validate_order(self, order: Order) -> Tuple[bool, str]:
        """
        Validate order before creating invoice.

        Args:
            order: Order to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if order has items
        if not order.items:
            return False, "No items in order (all items have qty=0 or price=0)"

        # Validate total matches sum of items
        if not order.validate_total(tolerance=0.01):
            calculated = sum(item.total_price for item in order.items)
            return False, f"Total mismatch: sheet={order.total_amount:.2f}, calculated={calculated:.2f}"

        return True, ""

    def _process_single_order(self, order: Order, stop_on_validation_error: bool = True) -> bool:
        """
        Process a single order (create invoice and update sheet).

        Args:
            order: Order to process
            stop_on_validation_error: If True, raise exception on validation errors

        Returns:
            True if successful, False if failed
        """
        try:
            logger.info(f"Processing order {order.row_id} for {order.customer_name}")

            # Validate order - STOP ENTIRE PROCESS IF VALIDATION FAILS
            is_valid, error_msg = self._validate_order(order)
            if not is_valid:
                logger.error(f"Order {order.row_id} validation failed: {error_msg}")
                self.sheets.mark_invoice_error(order.sheet_row_number, error_msg)

                if stop_on_validation_error:
                    logger.error("STOPPING: Fix the error before continuing!")
                    # Don't catch this exception - let it bubble up to stop the process
                    raise ValueError(f"Validation failed for {order.customer_name}: {error_msg}")
                else:
                    return False

            # Build receipt
            receipt = self._build_receipt(order)

            # Create invoice via Keep.co.il API
            logger.info(f"Creating invoice for {order.customer_name} (₪{order.total_amount:.2f})")
            response = self.keep.create_receipt(receipt.to_dict())

            # Extract invoice URL
            invoice_url = self.keep.get_receipt_url(response)

            if invoice_url:
                logger.info(f"Invoice created successfully: {invoice_url}")
                self.sheets.mark_invoice_created(order.sheet_row_number, invoice_url)
                return True
            else:
                error_msg = f"Invoice created but URL not found in response: {response}"
                logger.warning(error_msg)
                self.sheets.mark_invoice_error(order.sheet_row_number, error_msg)
                return False

        except ValueError as e:
            # Validation errors - re-raise to stop process if stop_on_validation_error is True
            if stop_on_validation_error and "Validation failed" in str(e):
                raise
            # Other ValueErrors
            error_msg = f"Error processing order: {str(e)}"
            logger.error(f"Order {order.row_id} failed: {error_msg}")
            self.sheets.mark_invoice_error(order.sheet_row_number, error_msg)
            return False
        except Exception as e:
            error_msg = f"Error processing order: {str(e)}"
            logger.error(f"Order {order.row_id} failed: {error_msg}")
            self.sheets.mark_invoice_error(order.sheet_row_number, error_msg)
            return False

    def process_pending_invoices(self, max_date: Optional[datetime] = None) -> dict:
        """
        Process all pending invoices from Google Sheets.

        Returns:
            Summary dictionary with counts of processed/succeeded/failed orders
        """
        logger.info("Starting invoice processing")

        # Get pending orders (with optional date filter)
        if max_date:
            logger.info(f"Processing orders up to {max_date.date()}")
        pending_orders = self.sheets.get_pending_orders(max_date=max_date)
        logger.info(f"Found {len(pending_orders)} pending orders")

        if not pending_orders:
            logger.info("No pending orders to process")
            return {
                "total": 0,
                "succeeded": 0,
                "failed": 0
            }

        # Process each order
        succeeded = 0
        failed = 0

        for order in pending_orders:
            success = self._process_single_order(order)

            if success:
                succeeded += 1
            else:
                failed += 1

        # Log summary
        logger.info(f"Processing complete: {succeeded} succeeded, {failed} failed out of {len(pending_orders)} total")

        return {
            "total": len(pending_orders),
            "succeeded": succeeded,
            "failed": failed
        }
