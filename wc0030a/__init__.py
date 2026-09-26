"""Steuerung der LogiLink WC0030A (OEM: Apexis APM-H803-MPC) per HTTP-CGI."""

from .api import Camera, CameraError
from .parser import parse_js_vars

__all__ = ["Camera", "CameraError", "parse_js_vars"]
__version__ = "0.2.0"
