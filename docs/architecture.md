# AWS ETL Architecture

## High-level flow
1. Source systems produce JSONL events into S3 `raw/`.
2. EventBridge triggers Step Functions every 15 minutes.
3. Step Functions executes Glue Ingestion then Glue Transformation jobs.
4. Ingestion validates schema, enforces idempotency, and writes to raw validated zone.
5. Transformation applies quality rules, partitions by `event_date`, and writes to curated zone.
6. Curated data is queried with Athena and can be exposed to Redshift external schema.

## Core AWS services
- **Ingestion**: AWS Glue job (`*-ingestion`)
- **Processing**: AWS Glue job (`*-transformation`)
- **Storage**: S3 data lake with KMS encryption
- **Orchestration**: Step Functions state machine
- **Scheduling**: EventBridge rule
- **Observability**: CloudWatch Logs + alarm for failed executions
- **Failure handling**: SQS dead-letter queue
- **Secrets**: Secrets Manager

## Security model
- Least privilege IAM roles for Glue, Step Functions, and EventBridge
- KMS customer-managed key for S3, logs, and DLQ encryption
- Public access blocked on S3 bucket
- Secret retrieval restricted to Glue role
