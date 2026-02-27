/*
This is a Terraform configuration file that creates Proxmox VMs using the BPG provider (bpg/proxmox).
The configuration file defines a list of VM definitions for different scenarios (ad-lab-xs, ad-lab-s, ad-lab-m, k8s-dev, jumphost)
and selects the VM definitions based on the scenario. The configuration file then creates a
Proxmox VM for each VM in the selected definition using the proxmox_virtual_environment_vm resource.
*/

locals {
  # Derive the first 3 octets and the 4th-octet start from the CIDR.
  # e.g. "192.168.0.0/24" → base "192.168.0", start 0
  subnet_base  = join(".", slice(split(".", split("/", var.subnet_cidr)[0]), 0, 3))
  subnet_start = tonumber(split(".", split("/", var.subnet_cidr)[0])[3])

  vm_definitions = {
    "ad-lab-xs" = [
      { name_suffix = "ad-1a",    role = "ad",      cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 10 },
      { name_suffix = "wutil-1a", role = "wutil",   cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 20 },
      { name_suffix = "gen-1a",   role = "general",  cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 30 },
    ]
    "ad-lab-s" = [
      { name_suffix = "ad-1a",    role = "ad",      cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 10 },
      { name_suffix = "wutil-1a", role = "wutil",   cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 20 },
      { name_suffix = "gen-1a",   role = "general",  cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 30 },
      { name_suffix = "gen-1b",   role = "general",  cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 31 },
    ]
    "ad-lab-m" = [
      { name_suffix = "ad-1a",    role = "ad",      cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 10 },
      { name_suffix = "ad-2a",    role = "ad",      cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 11 },
      { name_suffix = "wutil-1a", role = "wutil",   cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 20 },
      { name_suffix = "gen-1a",   role = "general",  cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 30 },
      { name_suffix = "gen-1b",   role = "general",  cpu = 2, disk_size = "40G", os_type = "windows", ip_offset = 31 },
    ]
    "k8s-dev" = [
      { name_suffix = "k8s-1a",   role = "ctrl",    cpu = 2, disk_size = "32G", os_type = "cloud-init", ip_offset = 40 },
      { name_suffix = "k8s-1b",   role = "ctrl",    cpu = 2, disk_size = "32G", os_type = "cloud-init", ip_offset = 41 },
      { name_suffix = "k8s-1c",   role = "ctrl",    cpu = 2, disk_size = "32G", os_type = "cloud-init", ip_offset = 42 },
      { name_suffix = "k8s-1d",   role = "work",    cpu = 4, disk_size = "32G", os_type = "cloud-init", ip_offset = 43 },
      { name_suffix = "k8s-1e",   role = "work",    cpu = 4, disk_size = "32G", os_type = "cloud-init", ip_offset = 44 },
    ]
    "jumphost" = [
      { name_suffix = "lutil-1a", role = "lutil",   cpu = 2, disk_size = "32G", os_type = "cloud-init", ip_offset = 15 },
    ]
  }
  environment_offsets = {
    "k8s-dev"   = 0
    "ad-lab-xs" = 25
    "ad-lab-s"  = 50
    "ad-lab-m"  = 75
    "jumphost"  = 100
  }
}

locals {
  selected_vms = local.vm_definitions[var.scenario]
}

module "vm" {
  source   = "../modules/proxmox-vm"
  for_each = {
    for vm in local.selected_vms :
    vm.name_suffix => vm
  }

  name              = "${var.environment_name_prefix}-${each.value.name_suffix}"
  role              = each.value.role
  cpu               = each.value.cpu
  memory            = lookup(each.value, "memory", var.default_memory)
  disk_size         = tonumber(replace(each.value.disk_size, "G", ""))
  os_type           = each.value.os_type
  template_id       = each.value.os_type == "windows" ? var.windows_template_id : var.linux_template_id
  ip_address        = "${local.subnet_base}.${local.subnet_start + each.value.ip_offset}/${split("/", var.subnet_cidr)[1]}"
  vm_gateway        = var.vm_gateway
  network_bridge    = var.network_bridge
  node_name         = var.node_name
  storage_pool      = var.storage_pool
  vm_id             = var.vm_id_start + local.environment_offsets[var.scenario] + index(keys({ for vm in local.selected_vms : vm.name_suffix => vm }), each.key)
  bios              = "ovmf"
  ansible_user      = var.ansible_user
  ssh_pub_key       = var.ssh_pub_key
  ci_password       = var.ci_password
  dns_servers       = var.dns_servers
}
