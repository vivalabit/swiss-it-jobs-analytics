from __future__ import annotations

import unittest

from swiss_jobs.core.throttle import RequestThrottle


class RequestThrottleTests(unittest.TestCase):
    def test_disabled_throttle_does_not_sleep(self) -> None:
        sleeps: list[float] = []
        throttle = RequestThrottle(
            min_seconds=0,
            max_seconds=0,
            sleep=sleeps.append,
            monotonic=lambda: 0.0,
        )

        throttle.wait()
        throttle.wait()

        self.assertEqual([], sleeps)

    def test_fixed_delay_reserves_spaced_request_starts_for_shared_workers(self) -> None:
        sleeps: list[float] = []
        throttle = RequestThrottle(
            min_seconds=0.25,
            max_seconds=0.25,
            sleep=sleeps.append,
            monotonic=lambda: 0.0,
        )

        throttle.wait()
        throttle.wait()
        throttle.wait()

        self.assertEqual([0.25, 0.5], sleeps)

    def test_jitter_uses_configured_bounds(self) -> None:
        sleeps: list[float] = []
        throttle = RequestThrottle(
            min_seconds=0.5,
            max_seconds=1.0,
            sleep=sleeps.append,
            monotonic=lambda: 0.0,
            uniform=lambda minimum, maximum: (minimum + maximum) / 2,
        )

        throttle.wait()
        throttle.wait()

        self.assertEqual([0.75], sleeps)


if __name__ == "__main__":
    unittest.main()
