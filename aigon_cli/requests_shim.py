#!/usr/bin/env python3
"""Minimal requests library replacement using urllib.

This module provides a minimal drop-in replacement for the requests library
using only Python's standard library (urllib). It implements only the features
actually used by the Aigon CLI client.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import json as json_module
import urllib.request
import urllib.parse
import urllib.error
from typing import Any, Dict, Optional


class HTTPError(Exception):
    """HTTP error exception."""
    pass


class Response:
    """Minimal response object that mimics requests.Response."""

    def __init__(self, urllib_response, url: str):
        """Initialize response from urllib response.

        Args:
            urllib_response: urllib response object or HTTPError
            url: The request URL
        """
        self._response = urllib_response
        self.url = url
        self.status_code = urllib_response.status if hasattr(urllib_response, 'status') else urllib_response.code
        self._content = None
        # Extract headers from urllib response
        self.headers = dict(urllib_response.headers) if hasattr(urllib_response, 'headers') else {}

    def json(self) -> Any:
        """Parse response as JSON.

        Returns:
            Parsed JSON data
        """
        if self._content is None:
            self._content = self._response.read()
        return json_module.loads(self._content.decode('utf-8'))

    @property
    def text(self) -> str:
        """Get response as text.

        Returns:
            Response body as string
        """
        if self._content is None:
            self._content = self._response.read()
        return self._content.decode('utf-8')

    @property
    def content(self) -> bytes:
        """Get response as bytes.

        Returns:
            Response body as bytes
        """
        if self._content is None:
            self._content = self._response.read()
        return self._content

    def raise_for_status(self) -> None:
        """Raise HTTPError if status code indicates error.

        Raises:
            HTTPError: If status code is 4xx or 5xx
        """
        if 400 <= self.status_code < 600:
            raise HTTPError(f"HTTP {self.status_code} error for URL: {self.url}")


def _build_url(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Build URL with query parameters.

    Args:
        url: Base URL
        params: Query parameters

    Returns:
        Complete URL with parameters
    """
    if not params:
        return url

    # Convert params to strings and encode
    query = urllib.parse.urlencode(params)
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}{query}"


def _make_request(method: str, url: str,
                 headers: Optional[Dict[str, str]] = None,
                 params: Optional[Dict[str, Any]] = None,
                 json: Optional[Any] = None,
                 data: Optional[str] = None) -> Response:
    """Make HTTP request using urllib.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        url: Request URL
        headers: Request headers
        params: Query parameters
        json: JSON data to send
        data: Raw data to send

    Returns:
        Response object

    Raises:
        HTTPError: If request fails
    """
    # Build full URL with params
    full_url = _build_url(url, params)

    # Prepare request body
    request_data = None
    request_headers = dict(headers) if headers else {}

    if json is not None:
        request_data = json_module.dumps(json).encode('utf-8')
        if 'Content-Type' not in request_headers:
            request_headers['Content-Type'] = 'application/json'
    elif data is not None:
        request_data = data.encode('utf-8') if isinstance(data, str) else data

    # Create request
    req = urllib.request.Request(
        full_url,
        data=request_data,
        headers=request_headers,
        method=method
    )

    # Make request and handle errors
    try:
        urllib_response = urllib.request.urlopen(req)
        return Response(urllib_response, full_url)
    except urllib.error.HTTPError as e:
        # Convert urllib HTTPError to our Response object
        # This allows checking status_code and calling json() on error responses
        return Response(e, full_url)
    except urllib.error.URLError as e:
        raise HTTPError(f"URL error: {e.reason}")


def get(url: str, headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None) -> Response:
    """Make GET request.

    Args:
        url: Request URL
        headers: Request headers
        params: Query parameters

    Returns:
        Response object
    """
    return _make_request('GET', url, headers=headers, params=params)


def post(url: str, headers: Optional[Dict[str, str]] = None,
         params: Optional[Dict[str, Any]] = None,
         json: Optional[Any] = None) -> Response:
    """Make POST request.

    Args:
        url: Request URL
        headers: Request headers
        params: Query parameters
        json: JSON data to send

    Returns:
        Response object
    """
    return _make_request('POST', url, headers=headers, params=params, json=json)


def put(url: str, headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[str] = None,
        json: Optional[Any] = None) -> Response:
    """Make PUT request.

    Args:
        url: Request URL
        headers: Request headers
        params: Query parameters
        data: Raw data to send
        json: JSON data to send

    Returns:
        Response object
    """
    return _make_request('PUT', url, headers=headers, params=params, data=data, json=json)


def patch(url: str, headers: Optional[Dict[str, str]] = None,
          params: Optional[Dict[str, Any]] = None,
          data: Optional[str] = None,
          json: Optional[Any] = None) -> Response:
    """Make PATCH request.

    Args:
        url: Request URL
        headers: Request headers
        params: Query parameters
        data: Raw data to send
        json: JSON data to send

    Returns:
        Response object
    """
    return _make_request('PATCH', url, headers=headers, params=params, data=data, json=json)


def delete(url: str, headers: Optional[Dict[str, str]] = None,
           params: Optional[Dict[str, Any]] = None) -> Response:
    """Make DELETE request.

    Args:
        url: Request URL
        headers: Request headers
        params: Query parameters

    Returns:
        Response object
    """
    return _make_request('DELETE', url, headers=headers, params=params)


# Create exceptions namespace to match requests library
class exceptions:
    """Exception classes matching requests.exceptions."""
    HTTPError = HTTPError
