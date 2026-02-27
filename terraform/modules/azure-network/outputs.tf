output "resource_group_name" {
  description = "Name of the resource group (looked up via data source)"
  value       = data.azurerm_resource_group.rg.name
}

output "resource_group_location" {
  description = "Location of the resource group (looked up via data source)"
  value       = data.azurerm_resource_group.rg.location
}

output "subnet_id" {
  description = "Subnet ID — passed to azure-vm module for NIC creation"
  value       = azurerm_subnet.subnet.id
}
