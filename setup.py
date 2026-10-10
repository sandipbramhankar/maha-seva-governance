from setuptools import setup, find_packages

setup(
    name="maha-seva-governance",
    version="0.1.0",
    description=(
        "Ticket-based governance platform for Maharashtra citizen services. "
        "Every request gets a Seva ID; every Seva ID gets an owner; "
        "every owner gets measured."
    ),
    author="Sandipkumar Prabhu Bramhankar",
    author_email="sandip.bramhankar@gmail.com",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.9",
    install_requires=[
        # indicer is vendored into indicer/ rather than installed; these
        # are its runtime dependencies. See indicer/VENDORED.md.
        "indic-transliteration>=2.3.57",
        "jellyfish>=1.0.0",
        "fastapi>=0.110.0",
        "uvicorn>=0.27.0",
        "pydantic>=2.6.0",
        "python-dateutil>=2.8.2",
    ],
    extras_require={"dev": ["pytest>=7.0.0"]},
)
