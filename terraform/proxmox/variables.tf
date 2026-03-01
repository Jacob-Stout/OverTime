variable "pm_api_url" {
  description = "Proxmox VE API endpoint (e.g., https://host:8006)"
  type        = string
}

variable "pm_user" {
  description = "Proxmox VE username (e.g., root@pam)"
  type        = string
}

variable "node_name" {
  description = "Proxmox Node Name"
  type        = string
}

variable "storage_pool" {
  description = "Proxmox Storage Pool"
  type        = string
}

variable "network_bridge" {
  description = "Proxmox Network Bridge"
  type        = string
}

variable "pm_tls_insecure" {
  description = "Skip TLS verification (BPG provider)"
  type        = bool
  default     = false
}

variable "vm_id_start" {
  description = "Starting VM ID"
  type        = number
  default     = 9000
}

variable "vm_gateway" {
  description = "IP Address of the VM Gateway"
  type        = string
}

variable "windows_template_id" {
  description = "Numeric VM ID of the Windows Template"
  type        = number
}

variable "linux_template_id" {
  description = "Numeric VM ID of the Linux Template"
  type        = number
}

variable "vm_list" {
  description = "List of VM definitions to provision. Each object specifies a single VM."
  type = list(object({
    name_suffix = string
    role        = string
    cpu         = number
    memory      = optional(number)
    disk_size   = string
    os_type     = string
    ip_offset   = number
  }))
}

variable "environment_name_prefix" {
  description = "Prefix for the environment name"
  type        = string
  default     = "dev"
}

variable "ssh_pub_key" {
  description = "SSH Key to use for the VMs"
  type        = string
}

variable "ci_password" {
  description = "VM initialization password (cloud-init on Linux, Cloudbase-Init on Windows)"
  type        = string
  sensitive   = true
}

variable "ansible_user" {
  description = "Bootstrap user created by cloud-init on Linux VMs; Ansible connects as this user"
  type        = string
  default     = "ot-bootstrap"
}

variable "subnet_cidr" {
  description = "Subnet CIDR for VM addressing (e.g. 192.168.0.0/24, 10.0.1.0/24)"
  type        = string
}

variable "default_memory" {
  description = "Default RAM in MB for all VMs. Per-VM overrides in vm_definitions take precedence."
  type        = number
  default     = 4096
}

variable "dns_servers" {
  description = "List of DNS server IPs passed to every VM"
  type        = list(string)
  default     = []
}