"""Independent trials of a study in worker processes, in the order of a serial run."""

from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from multiprocessing import get_context

from gemini import runtime
from gemini.ops.backend import forced_name
from gemini.study._utils import progress

_shared = {}
"""What a worker process holds: the arguments every item of the map shares."""


POLL = 0.05
"""Seconds the parent waits for a worker before it looks at the finished trials again."""


def _start(shared, state, backend, queue):
    """Set the runtime of a worker like its parent's, one process, and keep ``shared``.

    With a ``queue`` every trial the worker finishes is put on it, for the parent to count.
    """
    if queue is not None:
        progress.forwarding(lambda: queue.put(1))
    _shared["value"] = shared
    _shared["settings"] = runtime.settings(backend, **(state | {"processes": 1}))
    _shared["settings"].__enter__()


def _call(job):
    """Return ``function(shared, item)`` for a ``(function, item)`` job in a worker."""
    function, item = job
    return function(_shared["value"], item)


def mapped(function, shared, items):
    """Return ``[function(shared, item) for item in items]``, over the processes of the runtime.

    ``runtime.settings(processes=n)`` sets how many worker processes run the items; with one, or
    one item, they run here in turn. The items are independent and the results come back in the
    order of ``items``, the same numbers as a serial run: a worker applies the settings of its
    parent (the backend, the precision, the display units) with one process, so
    it starts no pool of its own. ``function`` is a module level function, and ``shared`` and
    every item and result can be pickled. A worker starts from a ``forkserver`` that has imported
    gemini, so a call pays that import once for the process, not for every worker.

    When ``gemini.study._utils.progress`` has a listener, the parent counts the trials the workers
    finish while it waits, and an exception of the listener (a ``Cancelled``) stops the workers
    and is raised.
    """
    count = min(runtime.get_processes(), len(items))
    if count <= 1:
        return [function(shared, item) for item in items]
    context = get_context("forkserver")
    context.set_forkserver_preload(["gemini"])
    listener = progress.listening()
    queue = None if listener is None else context.SimpleQueue()
    initargs = (shared, runtime.state(), forced_name(), queue)
    pool = ProcessPoolExecutor(count, mp_context=context, initializer=_start, initargs=initargs)
    try:
        futures = [pool.submit(_call, (function, item)) for item in items]
        _wait(futures, queue, listener)
        answers = [future.result() for future in futures]
    except BaseException:
        _stop(pool)
        raise
    pool.shutdown()
    return answers


def _wait(futures, queue, listener):
    """Wait for the ``futures``; count each trial a worker puts on ``queue`` while they run."""
    pending = set(futures)
    while pending:
        _count(queue, listener)
        pending = wait(pending, timeout=POLL, return_when=FIRST_COMPLETED).not_done
    _count(queue, listener)


def _count(queue, listener):
    """Tell ``listener`` of every trial now on ``queue``."""
    while queue is not None and not queue.empty():
        queue.get()
        listener()


def _stop(pool):
    """Stop the pool at once: queued items are dropped and the running workers are terminated."""
    workers = list(pool._processes.values())
    pool.shutdown(wait=False, cancel_futures=True)
    for worker in workers:
        worker.terminate()
    for worker in workers:
        worker.join()


def split(items):
    """Return ``items`` as as many consecutive parts as the runtime has processes, none empty.

    The parts keep the order, so ``mapped`` over them and a flattening of the answers is the
    answer for ``items`` one by one.
    """
    count = max(1, min(runtime.get_processes(), len(items)))
    size, extra = divmod(len(items), count)
    parts, first = [], 0
    for index in range(count):
        stop = first + size + (1 if index < extra else 0)
        parts.append(items[first:stop])
        first = stop
    return parts


def mapped_batches(function, shared, items):
    """Return ``[answer for each item]`` of ``function(shared, part)`` over the parts of ``items``.

    ``function`` takes a list of items and gives a list of answers; the parts go to the processes
    of the runtime, one each, and the answers join in the order of ``items``.
    """
    answers = mapped(function, shared, split(items))
    return [answer for part in answers for answer in part]
