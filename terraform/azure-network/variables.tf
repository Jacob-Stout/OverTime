variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "vnet_name" {
  description = "Virtual network name"
  type        = string
}

variable "vnet_cidr" {
  description = "VNet address space (CIDR)"
  type        = string
}

variable "environment_name_prefix" {
  description = "Environment name prefix for tagging"
  type        = string
}
