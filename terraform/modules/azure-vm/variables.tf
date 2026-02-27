variable "name" {
  description = "VM name"
  type        = string
}

variable "role" {
  description = "VM role tag (ad, wutil, general, lutil, ctrl, work)"
  type        = string
}

variable "os_type" {
  description = "OS type: 'linux' or 'windows'"
  type        = string

  validation {
    condition     = contains(["linux", "windows"], var.os_type)
    error_message = "os_type must be 'linux' or 'windows'."
  }
}

variable "vm_size" {
  description = "Azure VM size (e.g. Standard_B2s)"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name (must already exist — created by azure-network module)"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID from azure-network module"
  type        = string
}

variable "assign_public_ip" {
  description = "Create and attach a public IP to this VM's NIC"
  type        = bool
  default     = false
}

variable "private_ip_address" {
  description = "Static private IP within the subnet"
  type        = string
}

variable "admin_username" {
  description = "VM administrator username"
  type        = string
}

variable "admin_password" {
  description = "VM administrator password"
  type        = string
  sensitive   = true
}

variable "ssh_pub_key" {
  description = "SSH public key (Linux only; ignored for Windows)"
  type        = string
  default     = ""
}

variable "os_disk_size_gb" {
  description = "OS disk size in GB"
  type        = number
  default     = 30
}

variable "environment_prefix" {
  description = "Environment prefix for tagging"
  type        = string
}
