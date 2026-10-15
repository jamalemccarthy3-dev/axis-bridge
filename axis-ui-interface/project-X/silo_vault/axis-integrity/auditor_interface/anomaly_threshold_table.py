# ANOMALY_THRESHOLD: The Comparator Brain
# Purpose: Compares real-time telemetry against the threshold table.
import anomaly_threshold_table_tool as tool


def is_anomaly(metric_type, current_value):
    """True when the value is over the metric's limit. A metric with no limit raises ValueError (an unknown metric is not 'normal'); a value that is not a number raises TypeError."""
    limits = tool.get_thresholds()
    if metric_type not in limits:
        raise ValueError("no threshold for metric %r (have %s)" % (metric_type, sorted(limits)))
    if isinstance(current_value, bool) or not isinstance(current_value, (int, float)):
        raise TypeError("a metric value is a number, got %r" % (current_value,))
    return current_value > limits[metric_type]
