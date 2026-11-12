"""
Start rqt keeping its graph plugins readable inside the web VNC viewer.

rqt_graph and rqt_tf_tree query the ROS graph only once at startup, before
their node has discovered the rest of the system, so they open empty. They
also fit the graph to the view only when it is drawn, while noVNC resizes
the screen every time the browser panel changes size.

Run by LauncherRqt as a script inside the Robotics Backend, not imported.
"""

import sys

from python_qt_binding.QtCore import QEvent, QObject, QTimer
from python_qt_binding.QtWidgets import QApplication, QGraphicsView, QPushButton
from rqt_gui.main import Main

# Both plugins name their buttons the same way
REFRESH_BUTTON = "refresh_graph_push_button"
FIT_BUTTON = "fit_in_view_push_button"
REFRESH_DELAYS_MS = [3000, 8000]
FIT_DEBOUNCE_MS = 300


def click_buttons(name):
    for widget in QApplication.allWidgets():
        if isinstance(widget, QPushButton) and widget.objectName() == name:
            widget.click()


class FitOnResize(QObject):
    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: click_buttons(FIT_BUTTON))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize and isinstance(obj, QGraphicsView):
            self.timer.start(FIT_DEBOUNCE_MS)
        return False


class AutoRefreshMain(Main):
    def create_application(self, argv):
        app = super().create_application(argv)
        for delay in REFRESH_DELAYS_MS:
            QTimer.singleShot(delay, lambda: click_buttons(REFRESH_BUTTON))
        self.fit_on_resize = FitOnResize()
        app.installEventFilter(self.fit_on_resize)
        return app


if __name__ == "__main__":
    sys.exit(AutoRefreshMain().main())
