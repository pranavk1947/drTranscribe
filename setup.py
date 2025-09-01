"""
Setup script for DrTranscribe - AI Medical Transcription System
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

# Read requirements
requirements = (this_directory / "requirements.txt").read_text().strip().split('\n')
requirements = [req.strip() for req in requirements if req.strip() and not req.startswith('#')]

setup(
    name="drtranscribe",
    version="1.0.0",
    author="Loop Health",
    author_email="info@loophealth.com",
    description="AI-powered medical transcription and processing system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/loophealth/drtranscribe",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Healthcare Industry",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-cov>=4.1.0",
            "black>=23.11.0",
            "flake8>=6.1.0",
            "mypy>=1.7.1",
            "pre-commit>=3.6.0",
        ],
        "gpu": [
            "torch[cuda]>=2.1.2",
            "torchaudio[cuda]>=2.1.2",
        ],
        "all": [
            "pinecone-client>=2.2.4",
            "weaviate-client>=3.25.3",
            "qdrant-client>=1.7.0",
            "azure-cognitiveservices-speech>=1.34.0",
            "google-cloud-speech>=2.21.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "drtranscribe=main:main",
            "drtranscribe-api=api.app:main",
            "drtranscribe-setup=scripts.setup:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["config/*.yaml", "templates/*.html", "*.md"],
    },
    zip_safe=False,
    keywords="medical, transcription, ai, nlp, healthcare, hipaa",
    project_urls={
        "Bug Reports": "https://github.com/loophealth/drtranscribe/issues",
        "Source": "https://github.com/loophealth/drtranscribe",
        "Documentation": "https://drtranscribe.readthedocs.io/",
    },
)