// Filename: terraform.tf
terraform {
  required_version = ">= 1.0"
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

// Filename: variables.tf
variable "region" {
  description = "region"
  type        = string
  default     = "ap-northeast-2"
}

variable "db_name" {
  description = "DB name"
  type        = string
  default     = "shopping_db"
}

variable "db_username" {
  description = "master user"
  type        = string
  default     = "admin"
}

variable "db_password" {
  description = "master password"
  type        = string
  sensitive   = true
  default     = "password"
}

variable "domain_name" {
  description = "Domain name"
  type        = string
  default     = "rainhyeon.store"
}

// Filename: vpc.tf
resource "aws_vpc" "this" {
  cidr_block           = "10.10.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "shopping_vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "shopping_igw"
  }
}

// Filename: subnets.tf
resource "aws_subnet" "public_1" {
  vpc_id                                      = aws_vpc.this.id
  cidr_block                                  = "10.10.30.0/24"
  availability_zone                           = "ap-northeast-2a"
  map_public_ip_on_launch                     = true
  enable_resource_name_dns_a_record_on_launch = true

  depends_on = [aws_internet_gateway.this]

  tags = {
    Name = "shopping_subnet_public_1"
  }
}

resource "aws_subnet" "public_2" {
  vpc_id                                      = aws_vpc.this.id
  cidr_block                                  = "10.10.31.0/24"
  availability_zone                           = "ap-northeast-2c"
  map_public_ip_on_launch                     = true
  enable_resource_name_dns_a_record_on_launch = true

  depends_on = [aws_internet_gateway.this]

  tags = {
    Name = "shopping_subnet_public_2"
  }
}

resource "aws_subnet" "web_1" {
  vpc_id                                      = aws_vpc.this.id
  cidr_block                                  = "10.10.10.0/24"
  availability_zone                           = "ap-northeast-2a"
  enable_resource_name_dns_a_record_on_launch = true

  tags = {
    Name = "shopping_subnet_web_1"
  }
}

resource "aws_subnet" "web_2" {
  vpc_id                                      = aws_vpc.this.id
  cidr_block                                  = "10.10.11.0/24"
  availability_zone                           = "ap-northeast-2c"
  enable_resource_name_dns_a_record_on_launch = true

  tags = {
    Name = "shopping_subnet_web_2"
  }
}

resource "aws_subnet" "db_1" {
  vpc_id                                      = aws_vpc.this.id
  cidr_block                                  = "10.10.20.0/24"
  availability_zone                           = "ap-northeast-2a"
  enable_resource_name_dns_a_record_on_launch = true

  tags = {
    Name = "shopping_subnet_db_1"
  }
}

resource "aws_subnet" "db_2" {
  vpc_id                                      = aws_vpc.this.id
  cidr_block                                  = "10.10.21.0/24"
  availability_zone                           = "ap-northeast-2c"
  enable_resource_name_dns_a_record_on_launch = true

  tags = {
    Name = "shopping_subnet_db_2"
  }
}

// Filename: nat_gateway.tf
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "shopping_eip_nat"
  }
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public_1.id

  tags = {
    Name = "shopping_natgw"
  }

  depends_on = [aws_internet_gateway.this]
}

// Filename: route_tables.tf
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "shopping_rt_public"
  }
}

resource "aws_route_table" "web" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this.id
  }

  tags = {
    Name = "shopping_rt_web"
  }
}

resource "aws_route_table" "db" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "shopping_rt_db"
  }
}

resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "web_1" {
  subnet_id      = aws_subnet.web_1.id
  route_table_id = aws_route_table.web.id
}

resource "aws_route_table_association" "web_2" {
  subnet_id      = aws_subnet.web_2.id
  route_table_id = aws_route_table.web.id
}

resource "aws_route_table_association" "db_1" {
  subnet_id      = aws_subnet.db_1.id
  route_table_id = aws_route_table.db.id
}

resource "aws_route_table_association" "db_2" {
  subnet_id      = aws_subnet.db_2.id
  route_table_id = aws_route_table.db.id
}

// Filename: security_groups.tf
resource "aws_security_group" "alb" {
  name        = "shopping_sg_alb"
  description = "Security group for ALB"
  vpc_id      = aws_vpc.this.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "shopping_sg_alb"
  }
}

resource "aws_security_group" "web" {
  name        = "shopping_sg_web"
  description = "Security group for web servers"
  vpc_id      = aws_vpc.this.id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "shopping_sg_web"
  }
}

resource "aws_security_group" "db" {
  name        = "shopping_sg_db"
  description = "Security group for database"
  vpc_id      = aws_vpc.this.id

  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "shopping_sg_db"
  }
}

resource "aws_security_group" "bastion" {
  name        = "shopping_sg_bastion"
  description = "Security group for bastion host"
  vpc_id      = aws_vpc.this.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "shopping_sg_bastion"
  }
}

// Filename: iam.tf
resource "aws_iam_role" "ec2_ssm_role" {
  name = "shopping_ec2_ssm_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "shopping_ec2_ssm_role"
  }
}

resource "aws_iam_role_policy_attachment" "ec2_ssm_policy" {
  role       = aws_iam_role.ec2_ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "shopping_ec2_profile"
  role = aws_iam_role.ec2_ssm_role.name

  tags = {
    Name = "shopping_ec2_profile"
  }
}

// Filename: ec2.tf
resource "aws_instance" "bastion" {
  ami                    = "ami-0c593c3690c32e925"
  instance_type          = "t3.medium"
  subnet_id              = aws_subnet.public_1.id
  vpc_security_group_ids = [aws_security_group.bastion.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  tags = {
    Name = "shopping_bastion"
  }
}

resource "aws_instance" "web_1" {
  ami                    = "ami-08943a151bd468f4e"
  instance_type          = "t3.medium"
  subnet_id              = aws_subnet.web_1.id
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  tags = {
    Name = "shopping_web_1"
  }
}

resource "aws_instance" "web_2" {
  ami                    = "ami-08943a151bd468f4e"
  instance_type          = "t3.medium"
  subnet_id              = aws_subnet.web_2.id
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  tags = {
    Name = "shopping_web_2"
  }
}

// Filename: alb.tf
resource "aws_lb" "this" {
  name               = "shopping-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_1.id, aws_subnet.public_2.id]

  tags = {
    Name = "shopping_alb"
  }
}

resource "aws_lb_target_group" "web" {
  name     = "shopping-web-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.this.id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }

  tags = {
    Name = "shopping_tg_web"
  }
}

resource "aws_lb_target_group_attachment" "web_1" {
  target_group_arn = aws_lb_target_group.web.arn
  target_id        = aws_instance.web_1.id
  port             = 80
}

resource "aws_lb_target_group_attachment" "web_2" {
  target_group_arn = aws_lb_target_group.web.arn
  target_id        = aws_instance.web_2.id
  port             = 80
}

resource "aws_lb_listener" "web_http" {
  load_balancer_arn = aws_lb.this.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "web_https" {
  load_balancer_arn = aws_lb.this.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = aws_acm_certificate_validation.this.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }

  depends_on = [aws_acm_certificate_validation.this]
}

// Filename: rds.tf
resource "aws_db_parameter_group" "mysql" {
  family = "mysql8.0"
  name   = "shopping-mysql-params"

  parameter {
    name  = "time_zone"
    value = "Asia/Seoul"
  }

  tags = {
    Name = "shopping_db_params"
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "shopping-db-subnet-group"
  subnet_ids = [aws_subnet.db_1.id, aws_subnet.db_2.id]

  tags = {
    Name = "shopping_db_subnet_group"
  }
}

resource "aws_db_instance" "this" {
  identifier             = "shopping-db"
  allocated_storage      = 20
  storage_type           = "gp2"
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.medium"
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = aws_db_parameter_group.mysql.name
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  skip_final_snapshot    = true

  tags = {
    Name = "shopping_db"
  }
}

// Filename: acm.tf
resource "aws_acm_certificate" "this" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "shopping_cert"
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.this.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.this.zone_id
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

// Filename: route53.tf
resource "aws_route53_zone" "this" {
  name = var.domain_name

  tags = {
    Name = "shopping_zone"
  }
}

resource "aws_route53_record" "root" {
  zone_id = aws_route53_zone.this.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "www_onprem" {
  zone_id = aws_route53_zone.this.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"
  ttl     = 300
  records = ["34.22.91.176"]

  weighted_routing_policy {
    weight = 225
  }

  set_identifier = "www-onprem-weight-225"
}

resource "aws_route53_record" "www_alb" {
  zone_id = aws_route53_zone.this.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }

  weighted_routing_policy {
    weight = 0
  }

  set_identifier = "www-alb-weight-0"
}

// Filename: outputs.tf
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.this.id
}

output "alb_dns_name" {
  description = "DNS name of the load balancer"
  value       = aws_lb.this.dns_name
}

output "route53_zone_id" {
  description = "Route53 zone ID"
  value       = aws_route53_zone.this.zone_id
}

output "route53_name_servers" {
  description = "Route53 name servers"
  value       = aws_route53_zone.this.name_servers
}

output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.this.endpoint
}

output "bastion_public_ip" {
  description = "Public IP of bastion host"
  value       = aws_instance.bastion.public_ip
}

