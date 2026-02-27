output "vm_id" {
  description = "Proxmox VM ID"
  value       = proxmox_virtual_environment_vm.this.vm_id
}

output "name" {
  description = "VM name"
  value       = proxmox_virtual_environment_vm.this.name
}

output "ip_address" {
  description = "VM IP address (with CIDR) — echoes the input variable for stable output"
  value       = var.ip_address
}
