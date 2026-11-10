"""Adapters: concrete implementations of the domain ports.

Heavy third-party libraries are imported *inside* adapter constructors, so
the service starts (and tests run) without the optional ``voice`` extras.
"""
