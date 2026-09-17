"""Growth curves from replicate cultures, and the checks that make them comparable.

A GrowthCurve is one species' abundance over time in one replicate, with its time and abundance units. A
Replicate holds one curve per species: one for a monoculture, one for each partner in a co-culture (the
value in a co-culture is specific to a species, for example from per-strain qPCR).

`curve_features` extracts basic features from one curve (area under the curve, maximal abundance), over a
window that `shared_window` makes comparable across curves. New features (for example growth rates from
different methods) are added to FEATURES.

These are helpers for callers such as a CLI or GUI. Matching replicates on metadata happens upstream; the
checks here only refuse comparisons that are meaningless by construction (mixed units, missing species).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GrowthCurve:
    """One species' abundance over time in one replicate."""

    species: str
    times: tuple                  # strictly increasing time points
    values: tuple                 # abundance at each time point, specific to `species`
    time_unit: str                # e.g. "h"
    abundance_unit: str           # e.g. "OD600", "CFU/mL", "16S copies/mL"

    def __post_init__(self):
        object.__setattr__(self, "times", tuple(float(t) for t in self.times))
        object.__setattr__(self, "values", tuple(float(v) for v in self.values))
        if not self.species:
            raise ValueError("growth curve has no species")
        if len(self.times) != len(self.values):
            raise ValueError(f"{self.species}: {len(self.times)} time points but {len(self.values)} values")
        if len(self.times) < 2:
            raise ValueError(f"{self.species}: a growth curve needs at least two time points")
        if any(b <= a for a, b in zip(self.times, self.times[1:], strict=False)):
            raise ValueError(f"{self.species}: time points must be strictly increasing")
        if not self.time_unit or not self.abundance_unit:
            raise ValueError(f"{self.species}: time unit and abundance unit are required")


@dataclass(frozen=True)
class Replicate:
    """One replicate culture: a curve per species it contains."""

    curves: tuple                 # GrowthCurve, one per species
    name: str = ""

    def __post_init__(self):
        object.__setattr__(self, "curves", tuple(self.curves))
        species = [c.species for c in self.curves]
        if not species:
            raise ValueError(f"replicate {self.name!r} has no growth curves")
        if len(set(species)) != len(species):
            raise ValueError(f"replicate {self.name!r} has more than one curve for a species")

    @property
    def species(self) -> tuple:
        return tuple(c.species for c in self.curves)

    def curve(self, species: str) -> GrowthCurve | None:
        return next((c for c in self.curves if c.species == species), None)


def _label(rep: Replicate, role: str, i: int) -> str:
    return f"{role} replicate {rep.name or i}"


def check_replicate_sets(mono_a, mono_b, co, species_a: str, species_b: str) -> None:
    """Raise ValueError unless the three replicate sets can be compared.

    mono_a holds monocultures of species_a only, mono_b monocultures of species_b only, and every co-culture
    replicate holds a curve for exactly species_a and species_b. All curves in the three sets share one time
    unit and one abundance unit (no hours against days, no CFU against OD); units are not converted.
    """
    if species_a == species_b:
        raise ValueError("species A and species B must differ")
    sets = (("mono A", mono_a, (species_a,)), ("mono B", mono_b, (species_b,)),
            ("co-culture", co, (species_a, species_b)))
    curves = []
    for role, reps, expected in sets:
        if not reps:
            raise ValueError(f"no {role} replicates")
        for i, rep in enumerate(reps):
            if sorted(rep.species) != sorted(expected):
                raise ValueError(f"{_label(rep, role, i)} holds species {list(rep.species)}, "
                                 f"expected {list(expected)}")
            curves.extend((f"{_label(rep, role, i)}, {c.species}", c) for c in rep.curves)

    for attr, what in (("time_unit", "time units"), ("abundance_unit", "abundance units")):
        units = {getattr(c, attr) for _, c in curves}
        if len(units) > 1:
            by_unit = {}
            for label, c in curves:
                by_unit.setdefault(getattr(c, attr), []).append(label)
            detail = "; ".join(f"{u!r}: {', '.join(labels)}" for u, labels in sorted(by_unit.items()))
            raise ValueError(f"mixed {what} across replicate sets ({detail})")


def shared_window(curves) -> tuple:
    """(start, end) over which the curves are comparable.

    Every curve must start at the same time point, otherwise comparing areas under the curve is
    meaningless and ValueError is raised. The end is the earliest last time point, so no curve is
    extrapolated.
    """
    curves = list(curves)
    if not curves:
        raise ValueError("no growth curves")
    start = curves[0].times[0]
    if any(not math.isclose(c.times[0], start, rel_tol=1e-9, abs_tol=1e-9) for c in curves):
        starts = sorted({c.times[0] for c in curves})
        raise ValueError(f"growth curves start at different time points {starts}; "
                         "they are only comparable from a common start")
    return start, min(c.times[-1] for c in curves)


def _cut(curve: GrowthCurve, end: float | None) -> tuple:
    """The curve's points up to `end`, with a linearly interpolated point at `end` when it falls between
    two measurements."""
    times, values = curve.times, curve.values
    if end is None or math.isclose(end, times[-1], rel_tol=1e-9, abs_tol=1e-9):
        return times, values
    if not times[0] < end < times[-1]:
        raise ValueError(f"{curve.species}: window end {end} is outside the curve ({times[0]} to {times[-1]})")
    i = next(k for k, t in enumerate(times) if t >= end)
    if math.isclose(times[i], end, rel_tol=1e-9, abs_tol=1e-9):
        return times[:i + 1], values[:i + 1]
    t0, t1, v0, v1 = times[i - 1], times[i], values[i - 1], values[i]
    v_end = v0 + (v1 - v0) * (end - t0) / (t1 - t0)
    return times[:i] + (end,), values[:i] + (v_end,)


def _auc(times, values) -> float:
    """Area under the curve by the trapezoidal rule, with no baseline subtraction."""
    return sum((t1 - t0) * (v0 + v1) / 2
               for t0, t1, v0, v1 in zip(times, times[1:], values, values[1:], strict=False))


FEATURES = {
    "auc": _auc,
    "max": lambda times, values: max(values),
}


def curve_features(curve: GrowthCurve, end: float | None = None) -> dict:
    """Basic features of one growth curve, up to `end` (the whole curve by default): each name in FEATURES
    ("auc" in time unit times abundance unit, "max" in abundance unit) mapped to its value."""
    times, values = _cut(curve, end)
    return {name: fn(times, values) for name, fn in FEATURES.items()}
