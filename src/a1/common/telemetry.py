"""OpenTelemetry instrumentation for traces and metrics.

Completely no-op when settings.otlp_endpoint is empty.
"""

from a1.common.logging import get_logger

log = get_logger("telemetry")

# Module-level handles — safe to import even when OTLP is not configured.
# When disabled, tracer is a no-op tracer and counters/histograms silently discard data.
tracer = None
request_counter = None
request_duration = None
token_counter = None
cost_counter = None
error_counter = None

_initialized = False


def setup_telemetry(app, settings) -> None:
    """Initialize OpenTelemetry tracing and metrics. No-op if otlp_endpoint is empty."""
    global \
        tracer, \
        request_counter, \
        request_duration, \
        token_counter, \
        cost_counter, \
        error_counter, \
        _initialized

    if not settings.otlp_endpoint or _initialized:
        log.info("OpenTelemetry disabled (no otlp_endpoint configured)")
        return

    try:
        from opentelemetry import metrics as otel_metrics
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": "a1-trainer",
                "service.version": "0.1.0",
            }
        )

        # Traces
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
        )
        trace.set_tracer_provider(tracer_provider)
        tracer = trace.get_tracer("a1.proxy")

        # Metrics
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=settings.otlp_endpoint),
            export_interval_millis=30000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        otel_metrics.set_meter_provider(meter_provider)
        meter = otel_metrics.get_meter("a1.proxy")

        request_counter = meter.create_counter(
            "a1.requests.total", description="Total proxy requests"
        )
        request_duration = meter.create_histogram(
            "a1.requests.duration_ms", description="Request latency in ms"
        )
        token_counter = meter.create_counter(
            "a1.tokens.total", description="Total tokens processed"
        )
        cost_counter = meter.create_counter("a1.cost.usd", description="Total cost in USD")
        error_counter = meter.create_counter("a1.errors.total", description="Total errors")

        # Auto-instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)

        _initialized = True
        log.info(f"OpenTelemetry initialized, exporting to {settings.otlp_endpoint}")

    except ImportError as e:
        log.warning(f"OpenTelemetry packages not available: {e}")
    except Exception as e:
        log.error(f"Failed to initialize OpenTelemetry: {e}")


def record_otel_request(
    provider: str,
    model: str,
    task_type: str | None,
    latency_ms: int,
    cost_usd: float,
    prompt_tokens: int,
    completion_tokens: int,
    error: bool = False,
):
    """Record OTLP metrics for a request. No-op if not initialized."""
    if request_counter is not None:
        attrs = {"provider": provider, "model": model, "task_type": task_type or "unknown"}
        request_counter.add(1, attrs)
        request_duration.record(latency_ms, {"provider": provider})
        token_counter.add(prompt_tokens, {"type": "prompt", "provider": provider})
        token_counter.add(completion_tokens, {"type": "completion", "provider": provider})
        cost_counter.add(cost_usd, {"provider": provider})
        if error and error_counter:
            error_counter.add(1, attrs)
