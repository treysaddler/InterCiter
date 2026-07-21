"""Application services: the read-side projection, jobs, and review operations.

The rich immutable model is the system of record; everything here *derives* reader-
friendly, traversable views from it and never mutates scientific assertions in place.
"""
