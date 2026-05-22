# Terraform skeleton for AWS. Not a complete deployment — fill in VPC, IAM,
# and any private endpoints your security posture requires.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # Recommend a remote backend (S3 + DynamoDB lock table) for shared use.
  # backend "s3" { ... }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "stockmarket"
}

variable "environment" {
  type    = string
  default = "prod"
}

locals {
  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# --- Networking (stub) -------------------------------------------------------
# Production: bring an existing VPC or instantiate the
# terraform-aws-modules/vpc/aws module with private + public subnets across
# >= 2 AZs. Do not run the API in a public subnet.

# --- EKS (stub) --------------------------------------------------------------
# resource "aws_eks_cluster" "main" { ... }

# --- RDS Postgres ------------------------------------------------------------
resource "aws_db_subnet_group" "postgres" {
  name       = "${var.project}-postgres"
  subnet_ids = []  # fill in with your private subnet ids
  tags       = local.tags
}

resource "aws_db_instance" "postgres" {
  count                  = 0  # set to 1 once subnets + security group are wired
  identifier             = "${var.project}-postgres"
  engine                 = "postgres"
  engine_version         = "16.3"
  instance_class         = "db.t4g.medium"
  allocated_storage      = 100
  storage_type           = "gp3"
  storage_encrypted      = true
  multi_az               = true
  publicly_accessible    = false
  skip_final_snapshot    = false
  deletion_protection    = true
  backup_retention_period = 14
  username               = "trader"
  manage_master_user_password = true
  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  tags                   = local.tags
}

# --- S3 data lake ------------------------------------------------------------
resource "aws_s3_bucket" "data" {
  bucket = "${var.project}-data-${var.environment}"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- ECR for container images ------------------------------------------------
resource "aws_ecr_repository" "api" {
  name                 = "${var.project}/api"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  tags = local.tags
}

resource "aws_ecr_repository" "worker" {
  name                 = "${var.project}/worker"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  tags = local.tags
}
