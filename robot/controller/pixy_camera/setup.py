from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pixy-camera",
    version="1.0.0",
    author="EV3 Robot Project",
    description="Pixy2 camera interface for EV3 MicroPython with event-driven block detection",
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
        "Topic :: Multimedia :: Graphics :: Capture",
    ],
    python_requires=">=3.6",
    install_requires=[
        "event-handler>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
        ],
    },
    keywords="pixy camera, computer vision, ev3, micropython, robotics, object detection",
    include_package_data=True,
    package_data={
        "pixy_camera": ["pixycamev3/*.py"],
    },
)