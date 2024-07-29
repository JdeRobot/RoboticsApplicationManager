# Creating a new RAM launcher

This guide outlines the steps involved in creating a new RAM launcher. 

For the `launch_world` transition, which transitions the application from the connected state to the world_ready state, the file executed is `launcher_world.py`, and for the `prepare_visualization` transition, the file executed is `launcher_visualization.py`.

To create a new RAM launcher for the `prepare_visualization` transition, follow these steps:

1. Define the New Visualization Configuration

First, add a new entry to the `visualization` dictionary in `launcher_visualization.py`. Let's call this new entry `custom_visualization` and assume it uses two modules: `abc_module` and `xyz_module`.

```python
visualization = {
    # Existing configurations...
    "custom_visualization": [
        {
            "type": "module",
            "module": "abc_module",
            "display": ":1",
            "external_port": 1200,
            "internal_port": 6000,
        },
        {
            "type": "module",
            "width": 1280,
            "height": 720,
            "module": "xyz_module",
            "display": ":2",
            "external_port": 1300,
            "internal_port": 6001,
        },
    ],
}
```

2. Implement the Required Modules

Next, ensure that the modules specified in your new visualization setup (`abc_module` and `xyz_module`) are implemented and available for import.

- For `abc_module`:
Create a file named `launcher_abc_module.py` and implement the `LauncherAbcModule` class.

- For `xyz_module`:
Create a file named `launcher_xyz_module.py` and implement the `LauncherXyzModule` class.

3. Using the New Visualization Setup

Now, you can create an instance of `LauncherVisualization` with the new visualization setup and run it.

To create a new RAM launcher for `launch_world` transition, follow similar steps as above by adding a new entry to the `worlds` dictionary in the `launcher_world.py` file. 