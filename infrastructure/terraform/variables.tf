variable "project_name" {
  description = "Project name prefix for resources"
  type        = string
  default     = "motheg-etl"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be one of dev, stage, prod"
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "schedule_expression" {
  description = "EventBridge schedule expression"
  type        = string
  default     = "rate(15 minutes)"
}
