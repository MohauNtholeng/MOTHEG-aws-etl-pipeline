# Operations Runbook

## 1) Local validation
1. `python -m pip install -e .[dev]`
2. `make check`
3. `python -m motheg_etl`
4. Confirm output in `build/curated/event_date=*/data.jsonl`

## 2) Deploy infrastructure (per environment)
1. `cd infrastructure/terraform`
2. `terraform init`
3. `terraform workspace select <env> || terraform workspace new <env>`
4. `terraform apply -var="environment=<env>"`

## 3) Deploy ETL scripts to S3
Upload `src/motheg_etl/ingestion.py` and `src/motheg_etl/transformation.py` to:
- `s3://<data-lake-bucket>/scripts/ingestion.py`
- `s3://<data-lake-bucket>/scripts/transformation.py`

## 4) Execute and monitor
1. Trigger state machine manually from AWS Console or wait for schedule.
2. Monitor Step Functions execution history.
3. Inspect CloudWatch logs (`/aws/states/<prefix>-etl`).
4. Check `ExecutionsFailed` alarm state.
5. Inspect DLQ for failed payloads.

## 5) Incident response
- If ingestion fails due to schema drift, update `config/pipeline.json` schema and redeploy script.
- If transformation fails due to quality checks, inspect records in raw zone and correct source data.
- Replay by re-running state machine after fixing root cause.
