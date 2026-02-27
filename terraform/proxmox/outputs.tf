# Outputs for OverTime automation

output "jumphost_ip_address" {
  description = "IP address of the linux utility server"
  value = try(
    [for k, vm in module.vm : vm.ip_address if startswith(k, "lutil")][0],
    null
  )
}

output "all_vm_ips" {
  description = "Map of all VM names to their IP addresses"
  value = {
    for k, vm in module.vm :
    vm.name => vm.ip_address
  }
}

output "all_vm_ids" {
  description = "Map of all VM names to their VM IDs"
  value = {
    for k, vm in module.vm :
    vm.name => vm.vm_id
  }
}
