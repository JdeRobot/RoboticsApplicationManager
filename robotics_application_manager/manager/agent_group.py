"""Agent group abstraction for the Robotics Application Manager.

RAM's lifecycle operations (play / pause / resume / reset / stop) used to act on
a single application process. Multi-agent exercises (e.g. drone cat-and-mouse,
which runs a "cat" and a "mouse") need them to act on *all* the agents at once.

Rather than teaching the RAM FiniteStateMachine about multiple agents, the FSM
stays single-target: it fires one transition, and that transition fans the
operation out over every member of this group. So a single ``pause`` trigger
becomes "suspend agent0, suspend agent1, ... ", a single ``reset`` becomes a
sequence over each agent, and so on. The FSM definition never changes; only the
execution layer behind each handler iterates the group.

This holds N agents (1 for most exercises, 2 for cat-mouse, more in future
multi-robot exercises) and exposes the per-agent *process* operations. World /
simulator level calls (pause_sim, reset_sim) remain single calls in the manager,
because a shared Gazebo world has one physics clock and cannot be paused
per-agent.
"""

import os
import signal

import psutil

from robotics_application_manager.libs import stop_process_and_children
from robotics_application_manager.ram_logging import LogManager


class AgentGroup:
    """A set of agent processes managed as one unit.

    Each lifecycle method fans the operation out over every member, so callers
    treat the whole group as if it were a single agent.
    """

    def __init__(self):
        # name -> subprocess.Popen
        self._agents = {}

    # ----- membership -------------------------------------------------------

    def add(self, name, proc):
        """Register an agent process under a name (e.g. 'agentA', 'agentB')."""
        self._agents[name] = proc

    def clear(self):
        """Forget all members without touching the processes."""
        self._agents = {}

    def names(self):
        return list(self._agents.keys())

    def __len__(self):
        return len(self._agents)

    def __bool__(self):
        # Lets callers keep writing `if self.application_processes:`
        return bool(self._agents)

    def __iter__(self):
        return iter(self._agents.values())

    # ----- group lifecycle operations (each fans out over all members) ------

    def pause_all(self):
        """Suspend every agent process and its whole child tree (SIGSTOP)."""
        for proc in self._agents.values():
            self._apply_to_tree(proc, lambda child: child.suspend())

    def resume_all(self):
        """Resume every agent process and its whole child tree (SIGCONT)."""
        for proc in self._agents.values():
            self._apply_to_tree(proc, lambda child: child.resume())

    def signal_stop_all(self):
        """SIGSTOP each top-level agent process (used to gate them before
        the simulator unpauses, so no agent acts on a still-paused world)."""
        self._signal_all(signal.SIGSTOP)

    def signal_cont_all(self):
        """SIGCONT each top-level agent process (release after unpause)."""
        self._signal_all(signal.SIGCONT)

    def kill_all(self):
        """Terminate every agent process and its children, then empty the group."""
        for name, proc in self._agents.items():
            try:
                stop_process_and_children(proc)
            except Exception:
                LogManager.logger.exception(f"Error stopping agent '{name}'")
        self.clear()

    # ----- helpers ----------------------------------------------------------

    def _signal_all(self, sig):
        for proc in self._agents.values():
            try:
                os.kill(proc.pid, sig)
            except ProcessLookupError:
                pass

    @staticmethod
    def _apply_to_tree(proc, fn):
        """Run ``fn`` on the process and every descendant, tolerating races."""
        try:
            parent = psutil.Process(proc.pid)
            tree = parent.children(recursive=True)
            tree.append(parent)
            for child in tree:
                try:
                    fn(child)
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
