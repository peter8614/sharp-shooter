"""Reusable Sharp Shooter inference primitives.

This package deliberately has no Flask, Firebase, or AWS dependency so the
same prediction code can run in the legacy server, local tools, and a future
Lambda worker.
"""

from .inference import predict_video

__all__ = ["predict_video"]
