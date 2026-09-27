"""Alert thresholds, each with its provenance.

"Sourced" thresholds cite a published finding. "Heuristic" thresholds are CluckTalk's own choices for
early warning. They are not veterinary standards, and user-facing text must never present them as such.
"""

# Sourced: farms with mortality < 5% were more profitable than those > 10%
# (jebas.org/ojs/index.php/jebas/article/view/832, 2023; PRD Section 3).
CUM_MORTALITY_WATCH_PCT = 5.0
CUM_MORTALITY_ALERT_PCT = 10.0

# Heuristic: today's deaths at least 3x the trailing 7-day daily average, at least 0.1% of the flock,
# and at least 3 birds (so one death on a small farm is not an "alert").
MORTALITY_SPIKE_FACTOR = 3.0
MORTALITY_SPIKE_MIN_FRACTION = 0.001
MORTALITY_SPIKE_MIN_BIRDS = 3
MIN_BASELINE_DAYS = 3  # fewer prior days than this -> baseline comparisons are not computed

# Heuristic: sampled weight vs breed target at the same age.
WEIGHT_WATCH_RATIO = 0.90
WEIGHT_ALERT_RATIO = 0.80

# Heuristic: farm FCR above breed target FCR by this much. Farm FCR includes feed eaten by birds that
# later died, so it runs above the publisher's mortality-excluded definition. The margin allows for that.
FCR_WATCH_MARGIN = 0.10

# Heuristic: feed eaten per bird today vs the house's own trailing 3-day average
# (broilers: as a ratio to the breed curve, because intake grows daily).
FEED_DROP_WATCH_RATIO = 0.85
FEED_BASELINE_DAYS = 3

# Heuristic: layer hen-day production drop vs trailing 7-day average, in percentage points.
LAYING_DROP_WATCH_PTS = 5.0
LAYING_DROP_ALERT_PTS = 10.0

# Records older than this many days before as_of make the status "stale".
STALE_AFTER_DAYS = 1
