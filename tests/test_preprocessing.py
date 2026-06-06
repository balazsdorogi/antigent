"""Unit tests for fastp report parsing (no Docker required)."""

from pipeline.neoantigen_discovery.preprocessing import parse_fastp_metrics


def _qc(total_reads, total_bases, q20, q30):
    return {
        "total_reads": total_reads,
        "total_bases": total_bases,
        "q20_rate": q20,
        "q30_rate": q30,
    }


def test_parse_fastp_metrics_full():
    report = {
        "summary": {
            "before_filtering": _qc(1000, 100000, 0.95, 0.90),
            "after_filtering": _qc(980, 97000, 0.97, 0.93),
        },
        "filtering_result": {
            "passed_filter_reads": 980,
            "low_quality_reads": 15,
            "too_many_N_reads": 1,
            "too_short_reads": 4,
            "too_long_reads": 0,
        },
        "duplication": {"rate": 0.05},
        "adapter_cutting": {"adapter_trimmed_reads": 12},
    }
    m = parse_fastp_metrics(report)
    assert m.before_filtering.total_reads == 1000
    assert m.after_filtering.q30_rate == 0.93
    assert m.filtering.passed_filter_reads == 980
    assert m.filtering.too_short_reads == 4
    assert m.duplication_rate == 0.05
    assert m.adapter_trimmed_reads == 12


def test_parse_fastp_metrics_tolerates_missing_optional_sections():
    report = {
        "summary": {
            "before_filtering": _qc(10, 1000, 1.0, 1.0),
            "after_filtering": _qc(10, 1000, 1.0, 1.0),
        },
        "filtering_result": {"passed_filter_reads": 10},
    }
    m = parse_fastp_metrics(report)
    assert m.duplication_rate == 0.0
    assert m.adapter_trimmed_reads == 0
    assert m.filtering.low_quality_reads == 0
    assert m.filtering.too_short_reads == 0
