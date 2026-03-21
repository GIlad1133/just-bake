"""
Keep.co.il API client for invoice creation.
Handles OAuth authentication and receipt creation.
"""

import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import time
import os


class KeepClient:
    """Client for Keep.co.il income API."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize Keep.co.il API client.

        Args:
            client_id: Keep.co.il OAuth client ID
            client_secret: Keep.co.il OAuth client secret
            base_url: API base URL (default: https://api.keepo.co.il)
        """
        self.client_id = client_id or os.getenv('KEEP_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('KEEP_CLIENT_SECRET')
        self.base_url = base_url or os.getenv('KEEP_API_BASE_URL', 'https://api.keepo.co.il')

        if not self.client_id or not self.client_secret:
            raise ValueError("Keep.co.il credentials not provided. Set KEEP_CLIENT_ID and KEEP_CLIENT_SECRET")

        # Token caching
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def _is_token_valid(self) -> bool:
        """Check if cached token is still valid."""
        if self._access_token is None or self._token_expires_at is None:
            return False

        # Add 60-second buffer before expiration
        return datetime.now() < (self._token_expires_at - timedelta(seconds=60))

    def _get_token(self) -> str:
        """
        Get OAuth access token (with caching).

        Returns:
            Access token string

        Raises:
            Exception if token request fails
        """
        # Return cached token if still valid
        if self._is_token_valid():
            return self._access_token

        # Request new token
        token_url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "scope": "seller-api",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        try:
            # Use form-encoded data (not JSON) - as per Keep.co.il API
            response = requests.post(token_url, data=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            self._access_token = data['access_token']

            # Calculate expiration time (usually 3600 seconds = 1 hour)
            expires_in = data.get('expires_in', 3600)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            return self._access_token

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get Keep.co.il access token: {e}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[Any, Any]] = None,
        retry_count: int = 0,
        max_retries: int = 3
    ) -> Dict[Any, Any]:
        """
        Make authenticated API request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request payload
            retry_count: Current retry attempt
            max_retries: Maximum number of retries

        Returns:
            Response JSON data

        Raises:
            Exception if request fails after all retries
        """
        token = self._get_token()
        url = f"{self.base_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                headers=headers,
                timeout=30
            )

            # Handle 401 Unauthorized (token expired)
            if response.status_code == 401:
                # Clear cached token and retry once
                self._access_token = None
                self._token_expires_at = None

                if retry_count < 1:
                    time.sleep(1)
                    return self._make_request(method, endpoint, data, retry_count + 1, max_retries)

            # Handle rate limiting (429) or server errors (5xx)
            if response.status_code in [429, 500, 502, 503, 504]:
                if retry_count < max_retries:
                    # Exponential backoff: 2^retry_count seconds
                    wait_time = 2 ** retry_count
                    time.sleep(wait_time)
                    return self._make_request(method, endpoint, data, retry_count + 1, max_retries)

            # Raise for other error status codes
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            if retry_count < max_retries:
                wait_time = 2 ** retry_count
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, retry_count + 1, max_retries)
            else:
                raise Exception(f"Keep.co.il API request failed: {e}")

    @staticmethod
    def _convert_shekels_to_agorot(amount: float) -> int:
        """
        Convert shekels to agorot (1 shekel = 100 agorot).

        Args:
            amount: Amount in shekels

        Returns:
            Amount in agorot (rounded to nearest integer)
        """
        return int(round(amount * 100))

    def create_receipt(self, receipt_data: Dict[Any, Any]) -> Dict[Any, Any]:
        """
        Create a receipt/invoice via Keep.co.il income API.

        Args:
            receipt_data: Receipt data in Keep.co.il format (from KeepReceipt.to_dict())

        Returns:
            API response containing receipt details (including URL)

        Raises:
            Exception if receipt creation fails
        """
        response = self._make_request("POST", "/seller/api/documents/income", data=receipt_data)

        # Add delay to avoid rate limiting on subsequent requests
        time.sleep(2)

        return response

    def get_receipt_url(self, response: Dict[Any, Any]) -> Optional[str]:
        """
        Extract receipt URL from API response.

        Args:
            response: Response from create_receipt()

        Returns:
            Receipt URL or None if not found
        """
        # The exact path to the URL may vary - adjust based on actual API response
        # Common patterns based on actual Keep.co.il responses:
        # - response['payload']['url']  (actual format)
        # - response['url']
        # - response['data']['url']

        # Try actual format first (payload.url)
        if 'payload' in response and isinstance(response['payload'], dict) and 'url' in response['payload']:
            return response['payload']['url']
        # Try other common patterns
        elif 'url' in response:
            return response['url']
        elif 'data' in response and isinstance(response['data'], dict) and 'url' in response['data']:
            return response['data']['url']
        elif 'receipt' in response and isinstance(response['receipt'], dict) and 'url' in response['receipt']:
            return response['receipt']['url']

        # If URL not found, return None
        return None
