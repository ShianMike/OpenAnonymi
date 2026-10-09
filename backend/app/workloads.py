"""Content-free admission for expensive rendering on the single-worker runtime."""

from threading import BoundedSemaphore

render_slot = BoundedSemaphore(1)
