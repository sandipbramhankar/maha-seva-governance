from setuptools import setup, find_packages

setup(
    name="seva-governance",
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
        # seva/engine/verification.py and seva/engine/fraud.py import indicer
        # directly; without it the package does not import at all.
        "indicer-hetero-match @ git+https://github.com/sandipbramhankar/"
        "indicer-hetero-match.git@master",
        "fastapi>=0.110.0",
        "uvicorn>=0.27.0",
        "pydantic>=2.6.0",
        "python-dateutil>=2.8.2",
    ],
    extras_require={"dev": ["pytest>=7.0.0"]},
)
