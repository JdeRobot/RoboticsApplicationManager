class IRoboticsPythonApplication:
    def __init__(self, update_callback, exercise_server, gui_server):
        self.update_callback = update_callback
        self.exercise_server = exercise_server
        self.gui_server = gui_server

    def load_code(self, code: str) -> bool:
        raise NotImplementedError("Exercise brains must implement load_code")

    def run(self):
        raise NotImplementedError("Exercise brains must implement run")

    def stop(self):
        raise NotImplementedError("Exercise brains must implement stop")

    def pause(self):
        raise NotImplementedError("Exercise brains must implement pause")

    def resume(self):
        raise NotImplementedError("Exercise brains must implement resume")

    def restart(self):
        raise NotImplementedError("Exercise brains must implement restart")

    def terminate(self):
        raise NotImplementedError("Exercise brains must implement terminate")

    @property
    def is_alive(self):
        raise NotImplementedError("Exercise brains must implement is_alive")
