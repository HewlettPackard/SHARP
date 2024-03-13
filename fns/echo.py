"""Simple echo function to test serverless."""
from flask import request


def main() -> str:
    """Repeat back inputs."""
    return request.get_data().decode("utf-8")
