terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  prefix = "${var.project_name}-${var.environment}"
}

resource "aws_kms_key" "etl" {
  description             = "KMS key for MOTHEG ETL"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_s3_bucket" "data_lake" {
  bucket = "${local.prefix}-data-lake"
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.etl.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket                  = aws_s3_bucket.data_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "transition-raw-and-processed"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_secretsmanager_secret" "pipeline" {
  name       = "${local.prefix}/pipeline/config"
  kms_key_id = aws_kms_key.etl.arn
}

resource "aws_iam_role" "glue_job" {
  name = "${local.prefix}-glue-job-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "glue.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "glue_job" {
  name = "${local.prefix}-glue-job-policy"
  role = aws_iam_role.glue_job.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
        Resource = [aws_kms_key.etl.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.pipeline.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_glue_job" "ingestion" {
  name     = "${local.prefix}-ingestion"
  role_arn = aws_iam_role.glue_job.arn

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.data_lake.bucket}/scripts/ingestion.py"
    python_version  = "3"
  }

  glue_version     = "5.0"
  max_retries      = 2
  timeout          = 30
  number_of_workers = 2
  worker_type      = "G.1X"

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.data_lake.bucket}/tmp/"
  }
}

resource "aws_glue_job" "transformation" {
  name     = "${local.prefix}-transformation"
  role_arn = aws_iam_role.glue_job.arn

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.data_lake.bucket}/scripts/transformation.py"
    python_version  = "3"
  }

  glue_version      = "5.0"
  max_retries       = 2
  timeout           = 30
  number_of_workers = 2
  worker_type       = "G.1X"

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.data_lake.bucket}/tmp/"
  }
}

resource "aws_iam_role" "step_functions" {
  name = "${local.prefix}-step-functions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "states.amazonaws.com"
      }
    }]
  })
}

resource "aws_sqs_queue" "dlq" {
  name              = "${local.prefix}-etl-dlq"
  kms_master_key_id = aws_kms_key.etl.arn
}

resource "aws_iam_role_policy" "step_functions" {
  name = "${local.prefix}-step-functions-policy"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
        Resource = [aws_glue_job.ingestion.arn, aws_glue_job.transformation.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [aws_sqs_queue.dlq.arn]
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "state_machine" {
  name              = "/aws/states/${local.prefix}-etl"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.etl.arn
}

resource "aws_sfn_state_machine" "etl" {
  name     = "${local.prefix}-etl"
  role_arn = aws_iam_role.step_functions.arn

  definition = templatefile("${path.module}/../stepfunctions/etl_state_machine.asl.json", {
    ingestion_job_name      = aws_glue_job.ingestion.name
    transformation_job_name = aws_glue_job.transformation.name
    dlq_url                 = aws_sqs_queue.dlq.url
  })

  logging_configuration {
    include_execution_data = true
    level                  = "ALL"
    log_destination        = "${aws_cloudwatch_log_group.state_machine.arn}:*"
  }

  encryption_configuration {
    kms_key_id                    = aws_kms_key.etl.arn
    type                          = "CUSTOMER_MANAGED_KMS_KEY"
    kms_data_key_reuse_period_seconds = 300
  }
}

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${local.prefix}-etl-schedule"
  schedule_expression = var.schedule_expression
}

resource "aws_iam_role" "eventbridge" {
  name = "${local.prefix}-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge" {
  name = "${local.prefix}-eventbridge-policy"
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = [aws_sfn_state_machine.etl.arn]
      }
    ]
  })
}

resource "aws_cloudwatch_event_target" "state_machine" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "etl-state-machine"
  arn       = aws_sfn_state_machine.etl.arn
  role_arn  = aws_iam_role.eventbridge.arn

  dead_letter_config {
    arn = aws_sqs_queue.dlq.arn
  }

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 3
  }
}

resource "aws_cloudwatch_metric_alarm" "failed_executions" {
  alarm_name          = "${local.prefix}-etl-failed-executions"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Alarm when ETL state machine has failed executions"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.etl.arn
  }
}
