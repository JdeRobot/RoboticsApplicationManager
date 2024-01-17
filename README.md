# Robotics Application Manager (RAM) Repository

## Overview

This repository provides a framework for managing the lifecycle of robotics applications, enabling their remote execution, communication, and state management. It offers the following key features:

- *Remote execution of robotics applications*
- *Communication with applications through WebSocket servers*
- *State management using a state machine*
- *Process management for applications and ROS environments*
- *Introspection data about the system*
- *Logging for tracking application activity*

## Key Components

- *Manager (manager.py):*
    - Orchestrates application states (idle, connected, ready, running, paused)
    - Handles external commands (start, stop, load code, pause, resume, terminate, disconnect)
    - Launches applications and ROS environments
    - Interacts with applications through a defined interface
    - Provides introspection data about the system
      
- *Communication Modules:*
    - *WebSocket Servers (consumer.py, new_consumer.py):* Facilitate communication with clients
    - *JavaScript Client Library (comms_manager.js):* Enables client-side interaction
      
- *Application Interface:*
    - *Robotics Python Application Interface (robotics_python_application_interface.py):* Defines methods for loading code, managing execution, monitoring status, and receiving updates
      
- *Utility Functions:*
    - *Process Utilities (process_utils.py):* Handle process management, class loading, and system state checks
    - *Logging (log_manager.py):* Tracks application activity and potential issues
    - *Docker Thread (docker_thread.py):* Runs Docker commands in separate threads for enhanced control

 **## Usage**

1. **Prerequisites:**
    - Python 3.x: [https://www.python.org/downloads/](https://www.python.org/downloads/)
    - Required libraries (listed in `requirements.txt`)

2. **Installation:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Starting the Manager:**
    - Run `python manager.py`

4. **Connecting a Client:**
    - Use the provided JavaScript client library to connect to the WebSocket server and interact with the Manager.


## Contributing

### Organizational Guidelines:


**1. Fork:**
* Create a fork of this repository within the organization's GitHub account.


**2. Branch:**
* Create a descriptively named branch for your changes.


**3. Coding Style:**
* Adhere to the organization's coding style guidelines (link to guidelines).


**4. Testing:**
* Write thorough unit tests for any new code or modifications.


**5. Code Review:**
* Request code reviews from appropriate team members before merging.


**6. Pull Request:**
* Create a pull request to merge your changes into the main repository.


**7. Address Feedback:**
* Responsively address comments and feedback from reviewers.


## Additional Contribution Tips:

**1. Familiarize with Project Structure:** 
* Review the repository structure to understand component relationships.


**2. Communicate:**
* Ask questions and discuss ideas with team members through issue trackers or designated channels.


**3. Document Changes:**
* Clearly explain the purpose and impact of your modifications in pull requests.


**4. Test Thoroughly:**
* Ensure your changes don't introduce regressions or unexpected behavior.


## License

This project is licensed under the MIT License. See the LICENSE file for more details.
