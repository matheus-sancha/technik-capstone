import os

# The hosting server switches on OpenTelemetry by itself. Offline there is nowhere to send it.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
