import setuptools

setuptools.setup(
    name="ainb",
    version="0.1.0",
    packages=setuptools.find_packages(include=["ainb", "ainb.*"]),
    include_package_data=True,
    install_requires=["mmh3"],
    entry_points={
        "console_scripts" : [
            "ainb = ainb.__main__:main",
        ],
    }
)