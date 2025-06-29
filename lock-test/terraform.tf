terraform {
  backend "s3" {
    bucket = "woohyeon-total-infra-test-12"
    key    = "hat/infra/tfstate/back/terraform.tfstate"
    dynamodb_table = "terraform-lock-table"
    region = "ap-northeast-2"
  }
}


// Filename: variables.tf
variable "region" {
  description = "region"
  default     = "ap-northeast-2"
}

// Filename: terraform.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

// Filename: vpc.tf
resource "aws_vpc" "this" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "hat2_vpc"
  }
}

