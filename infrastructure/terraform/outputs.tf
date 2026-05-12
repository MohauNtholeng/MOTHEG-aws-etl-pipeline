output "data_lake_bucket_name" {
  value = aws_s3_bucket.data_lake.bucket
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.etl.arn
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}
