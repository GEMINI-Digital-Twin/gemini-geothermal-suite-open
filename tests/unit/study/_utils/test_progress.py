"""``on_progress`` of the study functions: counts, cancelling and no effect on the numbers."""

import pytest

import gemini as gm
from gemini.study._utils import progress
from tests.unit.study.conftest import shallow_case, shallow_plant
from tests.unit.study.test_minimize import DEPTH, searching
from tests.unit.study.test_study import run_settings, settings

PRICE = {"economics.energy.electricity": {"kind": "uniform", "min": 90, "max": 150}}
SAMPLES = 6


class Listener:
    """A progress callback that keeps what it was told and may cancel after ``stop`` calls."""

    def __init__(self, stop=None):
        """Keep the calls; cancel when ``done`` reaches ``stop``."""
        self.calls, self.stop = [], stop

    def __call__(self, done, total):
        """Keep the call, and cancel when asked."""
        self.calls.append((done, total))
        if self.stop is not None and done >= self.stop:
            raise gm.errors.Cancelled("stop")


def sampled(**keywords):
    """Return a sample of ``SAMPLES`` draws of the shallow plant."""
    case = shallow_case(uncertain=PRICE)
    return gm.study.sample(shallow_plant(), case, ["lcts"], SAMPLES, 3, **keywords)


def minimized(ranges=DEPTH, evaluations=10, **keywords):
    """Return a search of ``evaluations`` trials on each doublet count of ``ranges``."""
    return gm.study.minimize(searching(ranges), shallow_case(), "lcts", evaluations, 0, **keywords)


def test_a_batch_of_draws_is_counted_one_by_one(runs):
    """The draws of a sample run as one batch and are told one after another."""
    listener = Listener()
    sampled(on_progress=listener)
    assert listener.calls == [(number, SAMPLES) for number in range(1, SAMPLES + 1)]


def test_a_search_counts_its_batch_and_its_single_trials(runs):
    """Ten trials: the first population of five is a batch, the others run alone."""
    listener = Listener()
    minimized(on_progress=listener)
    assert listener.calls == [(number, 10) for number in range(1, 11)] and len(runs) == 10


def test_the_trials_of_every_doublet_count_are_told_in_one_count(runs):
    """Two counts of five trials."""
    listener = Listener()
    minimized(DEPTH | {"size.doublets": (1, 2)}, 5, on_progress=listener)
    assert listener.calls == [(number, 10) for number in range(1, 11)]


def test_sensitivity_counts_both_ends_of_each_value(runs):
    """Two ends for each of the uncertain values."""
    listener = Listener()
    case = shallow_case(uncertain=PRICE)
    gm.study.sensitivity(shallow_plant(), case, ["lcts"], on_progress=listener)
    assert listener.calls == [(1, 2), (2, 2)]


def test_cancelling_stops_the_search_before_its_later_trials(runs):
    """Cancelled after the seventh trial: the five of the batch and two more ran, no others."""
    with pytest.raises(gm.errors.Cancelled):
        minimized(on_progress=Listener(stop=7))
    assert len(runs) == 7


def test_cancelling_a_batch_propagates(runs):
    """Cancelled from the first draw of a batch raises the same class."""
    with pytest.raises(gm.errors.Cancelled):
        sampled(on_progress=Listener(stop=1))


def test_a_failure_of_the_callback_propagates(runs):
    """Any other exception of the callback is the caller's."""

    def broken(done, total):
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        sampled(on_progress=broken)


def test_the_callback_changes_nothing_of_the_result(runs):
    """The same trials, in the same order, with the same numbers."""

    def searched(**keywords):
        return gm.study.minimize(searching(DEPTH), shallow_case(), "lcts", 5, 0, **keywords)

    plain, watched = searched(), searched(on_progress=Listener())
    assert plain["best"] == watched["best"] and plain["history"] == watched["history"]


def test_the_callback_changes_nothing_of_a_sample(runs):
    """The same draws and metrics."""
    assert sampled().to_dict() == sampled(on_progress=Listener()).to_dict()


def test_a_search_that_ends_early_still_reaches_its_total():
    """``reach`` settles the count once."""
    listener = Listener()
    count = progress.Count(listener, 10)
    count.one()
    count.reach(10)
    count.reach(10)
    assert listener.calls == [(1, 10), (10, 10)]


def test_a_study_counts_a_pair_that_runs_no_trial_as_one(folder, runs):
    """The method ``run`` has no trials."""
    listener = Listener()
    gm.Study.from_dict(run_settings(), folder=folder).run(on_progress=listener)
    assert listener.calls == [(1, 1)]


def test_a_study_counts_the_trials_of_its_search(folder, runs):
    """The budget of the search."""
    listener = Listener()
    gm.Study.from_dict(settings(plants=["one.json"], metrics=["co2"]), folder=folder).run(
        on_progress=listener
    )
    assert listener.calls[-1] == (5, 5) and len(listener.calls) == 5
