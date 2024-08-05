# Dummy RAM Client Guide

The dummy client can be used for developing and debugging new RAM launchers. It executes the transitions `connect`, `launch_world`, and `prepare_visualization`. 

Contributors can test their new launchers by replacing the code in the files executed during these transitions with their own code. This allows for testing to ensure everything functions correctly before creating new launchers. 

During the `launch_world` step of the dummy client, the file executed is `simple_circuit_followingcam.launch.py`, and during the `prepare_visualization` transition, it is `launcher_gazebo_view.py`. The exercise simulation can be viewed via a VNC display at [http://127.0.0.1:6080/vnc.html](http://127.0.0.1:6080/vnc.html).

## Using the Dummy Client

1. Clone the RoboticsApplicationManager repository:
   ```
   git clone https://github.com/JdeRobot/RoboticsApplicationManager.git -b <src-branch>
   ```

2. Start a new Docker container using the RoboticsBackend image and keep it running in the background:
   ```
   docker run --rm -it -p 7164:7164 -p 6080:6080 -p 1108:1108 -p 7163:7163 jderobot/robotics-backend
   ```

3. Navigate to the test directory in the cloned RAM repository and run the dummy client file:
   ```
   cd RoboticsApplicationManager/test/
   python3 dummyclient.py
   ```

You can access the exercise simulation at [http://127.0.0.1:6080/vnc.html](http://127.0.0.1:6080/vnc.html).

To stop debugging, simply close the dummy client file using `Ctrl+D`.

