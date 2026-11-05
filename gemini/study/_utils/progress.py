"""Progress of a study: the trials finished out of the trials the call has to run.

The caller's ``on_progress(done, total)`` runs in the parent process after each finished trial,
also when the trials run in worker processes (they tell the parent through a queue, see
``gemini.study._utils.parallel``). One counter is active at a time in a process; the code that
finishes a trial calls ``finished`` and does not know whether anyone listens.
"""

from contextlib import contextmanager

_active = {"report": None}
"""The function that learns of a finished trial in this process, ``None`` without a listener."""


class Count:
    """The trials finished so far out of ``total``, told to ``callback(done, total)``."""

    def __init__(self, callback, total):
        """Count towards ``total`` and tell ``callback``; nothing is told yet."""
        self.callback, self.total, self.done = callback, total, 0

    def one(self):
        """Count one more finished trial and tell the callback."""
        self.done += 1
        self.callback(self.done, self.total)

    def reach(self, number):
        """Tell the callback once that ``number`` trials are done, when fewer were counted.

        A search that ends before its budget, and a method that runs no trial, are settled here, so
        that ``done`` reaches the count the caller was given.
        """
        if self.done < number:
            self.done = number
            self.callback(self.done, self.total)


@contextmanager
def counting(callback, total):
    """Count the trials finished in the block towards ``total`` and tell ``callback``.

    Without a ``callback`` this does nothing and yields ``None``; inside another count it takes
    the trials over until it ends.
    """
    if callback is None:
        yield None
        return
    count = Count(callback, total)
    before = _active["report"]
    _active["report"] = count.one
    try:
        yield count
    finally:
        _active["report"] = before


def finished():
    """Tell the active counter, if there is one, that a trial has finished."""
    if _active["report"] is not None:
        _active["report"]()


def listening():
    """Return the function that counts a finished trial here, or ``None`` without a listener."""
    return _active["report"]


def forwarding(put):
    """Count the trials finished in this process by calling ``put()``: a worker's way to tell."""
    _active["report"] = put
