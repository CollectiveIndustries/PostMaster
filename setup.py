from setuptools import find_packages, setup

setup(
    name="PostMaster",
    version="0.1.0",
    description="PostMaster email handling and classification system",
    author="Collective Industries",
    python_requires=">=3.11",
    packages=find_packages(include=["lib*", "providers*"]),
    install_requires=[
        "requests>=2.31",
        "beautifulsoup4",
        "pyyaml",
        "CollectiveCore @ git+ssh://git@github.com/CollectiveIndustries/CollectiveCore.git",
    ],
    entry_points={"console_scripts": ["frostwarden=FrostWardenSanctum:main"]},  # assuming you define a main() function
    include_package_data=True,
)
