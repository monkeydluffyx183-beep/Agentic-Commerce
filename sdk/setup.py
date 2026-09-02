"""
Agent Commerce SDK setup.py

Install with: pip install -e ./sdk
"""

from setuptools import setup, find_packages

setup(
    name="agent-commerce-sdk",
    version="0.1.0",
    description="Agent Commerce SDK for AI-powered commerce on Shopify + Razorpay",
    author="Agent Commerce Team",
    author_email="team@agentcommerce.dev",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        "httpx>=0.27.0",
        "pydantic>=2.0.0",
        "mcp>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0",
            "ruff>=0.4.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
        "Topic :: Office/Business :: Financial",
    ],
)
