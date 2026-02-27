output "vm_id" {
  description = "Azure VM resource ID"
  value = (
    var.os_type == "linux"
    ? azurerm_linux_virtual_machine.linux[0].id
    : azurerm_windows_virtual_machine.windows[0].id
  )
}

output "name" {
  description = "VM name"
  value       = var.name
}

output "private_ip_address" {
  description = "Static private IP from the NIC"
  value       = azurerm_network_interface.nic.private_ip_address
}

output "public_ip_address" {
  description = "Public IP address, or null if not assigned"
  value       = var.assign_public_ip ? azurerm_public_ip.pip[0].ip_address : null
}
