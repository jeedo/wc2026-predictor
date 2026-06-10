import logging

# Suppress raw HTTP wire logs from the Azure SDK (Request URL, Response headers, etc.)
# These are emitted at INFO by default and flood Application Insights with noise.
logging.getLogger("azure.cosmos").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
