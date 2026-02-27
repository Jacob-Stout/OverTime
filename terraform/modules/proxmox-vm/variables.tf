variable "name" {
  description = "Full VM name (prefix already included)"
  type        = string
}

variable "role" {
  description = "VM role tag (ad, wutil, general, lutil, ctrl, work)"
  type        = string
}

variable "cpu" {
  description = "Number of CPU cores"
  type        = number
}

variable "memory" {
  description = "Memory in MiB"
  type        = number
}

variable "disk_size" {
  description = "Disk size in GiB (numeric, no suffix)"
  type        = number
}

variable "os_type" {
  description = "OS type: 'cloud-init' (Linux) or 'windows'"
  type        = string
}

variable "template_id" {
  description = "Numeric VM ID of the clone source template"
  type        = number
}

variable "ip_address" {
  description = "Static IP with CIDR (e.g. 192.168.0.10/24)"
  type        = string
}

variable "vm_gateway" {
  description = "Default gateway IP"
  type        = string
}

variable "network_bridge" {
  description = "Proxmox network bridge (e.g. vmbr2)"
  type        = string
}

variable "node_name" {
  description = "Proxmox node name"
  type        = string
}

variable "storage_pool" {
  description = "Proxmox storage pool for disk and cloud-init ISO"
  type        = string
}

variable "vm_id" {
  description = "Proxmox VM ID"
  type        = number
}

variable "bios" {
  description = "BIOS type (ovmf or seabios)"
  type        = string
  default     = "ovmf"
}

variable "ansible_user" {
  description = "Bootstrap user created by cloud-init on Linux VMs; Ansible connects as this user"
  type        = string
}

variable "ssh_pub_key" {
  description = "SSH public key for the ansible user"
  type        = string
}

variable "ci_password" {
  description = "Cloud-init user password"
  type        = string
  sensitive   = true
}

variable "dns_servers" {
  description = "List of DNS server IPs"
  type        = list(string)
  default     = []
}
