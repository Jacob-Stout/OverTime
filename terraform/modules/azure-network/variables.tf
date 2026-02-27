variable "resource_group_name" {
  description = "Existing resource group name (looked up via data source)"
  type        = string
}

variable "vnet_name" {
  description = "Virtual network name"
  type        = string
}

variable "vnet_cidr" {
  description = "VNet address space"
  type        = string
}

variable "subnet_name" {
  description = "Subnet name within the VNet"
  type        = string
}

variable "subnet_cidr" {
  description = "Subnet address space (must be within vnet_cidr)"
  type        = string
}

variable "environment_prefix" {
  description = "Environment prefix for tagging"
  type        = string
}

variable "allowed_source_prefix" {
  description = "Source address prefix for inbound NSG rules (SSH, RDP, WinRM). Set to your public IP or CIDR to restrict access. Default '*' allows connections from any source."
  type        = string
  default     = "*"
}
