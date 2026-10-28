from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Trajectory:
    time_s: NDArray[np.float64]
    output_points_mm: NDArray[np.float64]

    def __post_init__(self) -> None:
        if self.time_s.ndim != 1:
            raise ValueError("time_s must be one-dimensional")
        if self.output_points_mm.shape != (self.time_s.shape[0], 2):
            raise ValueError("output_points_mm must have shape (len(time_s), 2)")
