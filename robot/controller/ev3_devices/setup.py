from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="ev3-devices",
    version="1.0.0",
    author="EV3 Robot Project",
    description="Device management and drive systems for LEGO MINDSTORMS EV3 robots",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Hardware",
        "Topic :: Scientific/Engineering",
        "Topic :: Education",
    ],
    python_requires=">=3.6",
    install_requires=[
        "error-reporting>=1.0.0",
        # pybricks is only available on EV3 - not listed as requirement
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
        ],
    },
    keywords="ev3, lego mindstorms, robotics, micropython, motors, sensors, drive systems",
)