"""Ovládání foťáků Canon přes oficiální EDSDK (jen Windows, 64 bit)."""

from .camera import EdsdkCamera

__all__ = ["EdsdkCamera"]
