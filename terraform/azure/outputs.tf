output "jumphost_ip_address" {
  description = "Reachable IP of the linux utility server — public if assigned, else private. Null if no lutil VM."
  value = try(
    coalesce(
      [for k, vm in module.vm : vm.public_ip_address if startswith(k, "lutil")][0],
      [for k, vm in module.vm : vm.private_ip_address if startswith(k, "lutil")][0]
    ),
    null
  )
}

output "jumphost_public_ip" {
  description = "Public IP of the linux utility server, or null if not assigned"
  value = try(
    [for k, vm in module.vm : vm.public_ip_address if startswith(k, "lutil")][0],
    null
  )
}

output "wutil_ip_address" {
  description = "Reachable IP of the wutil VM — public if assigned, else private. Null if no wutil VM."
  value = try(
    coalesce(
      [for k, vm in module.vm : vm.public_ip_address if startswith(k, "wutil")][0],
      [for k, vm in module.vm : vm.private_ip_address if startswith(k, "wutil")][0]
    ),
    null
  )
}

output "wutil_public_ip" {
  description = "Public IP of the wutil VM, or null if not assigned"
  value = try(
    [for k, vm in module.vm : vm.public_ip_address if startswith(k, "wutil")][0],
    null
  )
}

output "all_vm_ips" {
  description = "Map of VM name to private IP (used for Ansible inventory)"
  value = {
    for k, vm in module.vm :
    vm.name => vm.private_ip_address
  }
}

output "all_vm_ids" {
  description = "Map of VM name to Azure resource ID"
  value = {
    for k, vm in module.vm :
    vm.name => vm.vm_id
  }
}
