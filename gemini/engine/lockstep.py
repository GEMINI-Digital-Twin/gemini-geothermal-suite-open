"""Many runs side by side: answer the executor requests of several runs together.

A run is a generator of ``Request`` objects (``gemini.engine.executor``). ``lockstep`` starts the
runs one after the other, collects the request each one stops at, hands the requests that an
executor can ``batchable`` evaluate together to its ``run_batch`` (one array pass for all of
them), runs the others alone, and sends each run its answer. Each run goes on in a context of its
own, so the runtime settings it enters are its own. A ``restore`` function of a run is called before
the run goes on and before a request of it that runs alone, for runs that share a plant.
"""

import contextvars


class Lane:
    """One run: its generator, the context it runs in and the function that restores its plant."""

    def __init__(self, steps, restore=None):
        """Keep the generator ``steps``; ``restore()`` puts the shared state of the run back."""
        self.steps = steps
        self.restore = restore
        self.context = contextvars.copy_context()
        self.result = None
        self.request = None

    def advance(self, send=None, throw=None):
        """Go on to the next request, or finish with the value of the generator."""
        if self.restore is not None and self.request is not None:
            self.restore()
        self.request = None
        try:
            if throw is not None:
                self.request = self.context.run(self.steps.throw, throw)
            else:
                self.request = self.context.run(self.steps.send, send)
        except StopIteration as stop:
            self.result = stop.value

    def close(self):
        """Stop the generator, in its own context."""
        self.context.run(self.steps.close)

    def run_alone(self):
        """Return the answer of the pending request, run alone with the plant as the run has it."""
        if self.restore is not None:
            self.restore()
        try:
            return self.context.run(self.request.run)
        except Exception as error:
            return error


def lockstep(lanes):
    """Run the ``lanes`` to their end and return the value of each one's generator.

    An exception a run does not catch stops all the runs and is raised.
    """
    try:
        for lane in lanes:
            lane.advance()
        while any(lane.request is not None for lane in lanes):
            _round([lane for lane in lanes if lane.request is not None])
    except BaseException:
        for lane in lanes:
            lane.close()
        raise
    return [lane.result for lane in lanes]


def _round(waiting):
    """Answer the pending request of every waiting lane and let each lane go on."""
    for lane, answer in zip(waiting, _answers(waiting)):
        if isinstance(answer, Exception):
            lane.advance(throw=answer)
        else:
            lane.advance(send=answer)


def _answers(waiting):
    """Return the answer of the request of each waiting lane: a result, or the exception raised."""
    answers = [None] * len(waiting)
    together = {}
    for position, lane in enumerate(waiting):
        request = lane.request
        if request.executor.batchable(request.prepared):
            together.setdefault(type(request.executor), []).append(position)
        else:
            answers[position] = lane.run_alone()
    for positions in together.values():
        executor = waiting[positions[0]].request.executor
        calls = [
            (waiting[i].request.prepared, waiting[i].request.rows, waiting[i].request.context)
            for i in positions
        ]
        for position, answer in zip(positions, executor.run_batch(calls)):
            answers[position] = answer
    return answers
