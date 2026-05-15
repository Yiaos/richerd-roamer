from setuptools import setup

package_name = "roamer_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Richerd",
    maintainer_email="richerd@example.invalid",
    description="ROS2 substrate bridge package for roamerd motion.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "valetudo_bridge_node = roamer_ros.valetudo_bridge_node:main",
            "mock_nav_node = roamer_ros.mock_nav_node:main",
        ],
    },
)
