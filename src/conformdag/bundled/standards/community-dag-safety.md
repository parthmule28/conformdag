# Community DAG Safety Standards

## Execution safety

Tasks use bounded timeouts and retries, and module-level code avoids high-confidence
I/O that can run at DAG import time.
