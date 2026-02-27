variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
}

variable "vnet_name" {
  description = "VNet name"
  type        = string
}

variable "vnet_cidr" {
  description = "VNet address space"
  type        = string
}

variable "subnet_cidr" {
  description = "Subnet address space"
  type        = string
}

variable "environment_name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "scenario" {
  description = "Environment scenario (e.g. ad-lab-m, k8s-dev, jumphost).  Must match a key in vm_definitions."
  type        = string

  validation {
    condition     = contains(["ad-lab-xs", "ad-lab-s", "ad-lab-m", "k8s-dev", "jumphost"], var.scenario)
    error_message = "scenario must be one of: ad-lab-xs, ad-lab-s, ad-lab-m, k8s-dev, jumphost"
  }
}

variable "default_vm_size" {
  description = "Default Azure VM size. Per-VM overrides in vm_definitions take precedence."
  type        = string
  default     = "Standard_B2s"
}

variable "allowed_source_prefix" {
  description = "Source IP/CIDR for NSG inbound rules. Default '*' permits inbound from any internet source — set to your public IP or CIDR to restrict access."
  type        = string
  default     = "*"
}

variable "admin_username" {
  description = "VM administrator username"
  type        = string
}

variable "admin_password" {
  description = "VM administrator password — passed via TF_VAR_admin_password, never in tfvars.json"
  type        = string
  sensitive   = true
}

variable "ssh_pub_key" {
  description = "SSH public key for Linux VMs"
  type        = string
  default     = ""
}
